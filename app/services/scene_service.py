from pathlib import Path
from typing import Optional
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

from app.models import ProjectState, SegmentAnalysis, FrameData, PipelineStep
from app.config import settings
from app.services.project_store import project_store
from app.utils.ffmpeg import extract_frame
from app.utils.logger import get_logger

logger = get_logger(__name__)


def detect_scenes(video_path: Path, threshold: float = 27.0) -> list[tuple[float, float]]:
    """
    Detect scene changes in a video.
    Returns list of (start_time, end_time) tuples.
    """
    video = open_video(str(video_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold))

    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()

    if not scene_list:
        # No scene changes detected, treat whole video as one scene
        from app.utils.ffmpeg import get_video_metadata
        metadata = get_video_metadata(video_path)
        return [(0.0, metadata.duration)]

    segments = []
    for scene in scene_list:
        start_time = scene[0].get_seconds()
        end_time = scene[1].get_seconds()
        segments.append((start_time, end_time))

    return segments


def merge_short_segments(
    segments: list[tuple[float, float]],
    min_duration: float = 2.0
) -> list[tuple[float, float]]:
    """Merge segments shorter than min_duration with adjacent segments."""
    if not segments:
        return segments

    merged = []
    current_start, current_end = segments[0]

    for start, end in segments[1:]:
        if current_end - current_start < min_duration:
            # Extend current segment
            current_end = end
        else:
            merged.append((current_start, current_end))
            current_start, current_end = start, end

    merged.append((current_start, current_end))
    return merged


def _merge_to_limit(
    segments: list[tuple[float, float]],
    max_segments: int
) -> list[tuple[float, float]]:
    """Merge segments to fit within max_segments limit."""
    if len(segments) <= max_segments:
        return segments

    # Calculate how many segments need to be merged
    while len(segments) > max_segments:
        # Find the shortest segment and merge it with its neighbor
        min_duration = float('inf')
        min_idx = 0

        for i, (start, end) in enumerate(segments):
            duration = end - start
            if duration < min_duration:
                min_duration = duration
                min_idx = i

        # Merge with the shorter neighbor
        if min_idx == 0:
            # First segment, merge with next
            segments = [(segments[0][0], segments[1][1])] + segments[2:]
        elif min_idx == len(segments) - 1:
            # Last segment, merge with previous
            segments = segments[:-2] + [(segments[-2][0], segments[-1][1])]
        else:
            # Middle segment, merge with shorter neighbor
            prev_dur = segments[min_idx - 1][1] - segments[min_idx - 1][0]
            next_dur = segments[min_idx + 1][1] - segments[min_idx + 1][0]

            if prev_dur <= next_dur:
                # Merge with previous
                new_seg = (segments[min_idx - 1][0], segments[min_idx][1])
                segments = segments[:min_idx - 1] + [new_seg] + segments[min_idx + 1:]
            else:
                # Merge with next
                new_seg = (segments[min_idx][0], segments[min_idx + 1][1])
                segments = segments[:min_idx] + [new_seg] + segments[min_idx + 2:]

    return segments


def extract_segment_frames(
    video_path: Path,
    segment: tuple[float, float],
    segment_id: int,
    output_dir: Path,
    num_frames: int = 5
) -> list[FrameData]:
    """Extract key frames from a segment."""
    start, end = segment
    duration = end - start
    frames = []

    # Calculate timestamps for frame extraction
    if num_frames == 1:
        timestamps = [start + duration / 2]
    else:
        step = duration / (num_frames + 1)
        timestamps = [start + step * (i + 1) for i in range(num_frames)]

    for i, ts in enumerate(timestamps):
        frame_path = output_dir / f"segment_{segment_id:03d}_frame_{i:02d}.jpg"

        if extract_frame(video_path, ts, frame_path):
            frames.append(FrameData(
                frame_path=str(frame_path),
                timestamp=ts
            ))
        else:
            logger.warning(f"Failed to extract frame at {ts:.2f}s")

    return frames


async def segment_video(state: ProjectState) -> ProjectState:
    """
    Segment video and extract frames.

    1. Detect scene changes
    2. Merge short segments
    3. Extract key frames from each segment
    """
    video_path = Path(state.input_video)
    project_dir = project_store.get_project_dir(state.project_id)
    frames_dir = project_dir / "frames"

    logger.info(f"Detecting scenes in {video_path}")

    # Update state to segmenting
    state = state.model_copy(update={"current_step": PipelineStep.SEGMENTING})
    project_store.save_state(state)

    # Detect scenes
    segments = detect_scenes(video_path, threshold=settings.scene_threshold)
    logger.info(f"Detected {len(segments)} initial scenes")

    # Merge short segments
    segments = merge_short_segments(segments, min_duration=settings.min_segment_duration)
    logger.info(f"After merging: {len(segments)} segments")

    # Limit max segments to prevent very long processing
    if len(segments) > settings.max_segments:
        logger.warning(f"Too many segments ({len(segments)}), limiting to {settings.max_segments}")
        # Merge segments to fit within limit
        segments = _merge_to_limit(segments, settings.max_segments)
        logger.info(f"After limiting: {len(segments)} segments")

    # Update state to extracting frames
    state = state.model_copy(update={"current_step": PipelineStep.EXTRACTING_FRAMES})
    project_store.save_state(state)

    # Extract frames for each segment
    segment_analyses = []
    for i, (start, end) in enumerate(segments):
        logger.info(f"Extracting frames for segment {i+1}/{len(segments)} ({start:.1f}s - {end:.1f}s)")

        frames = extract_segment_frames(
            video_path,
            (start, end),
            i,
            frames_dir,
            num_frames=settings.frames_per_segment
        )

        segment_analyses.append(SegmentAnalysis(
            segment_id=i,
            start_time=start,
            end_time=end,
            frames=frames
        ))

    # Update state with segments
    state = state.model_copy(update={"segments": segment_analyses})
    project_store.save_state(state)

    logger.info(f"Segmentation complete: {len(segment_analyses)} segments, {sum(len(s.frames) for s in segment_analyses)} frames")
    return state
