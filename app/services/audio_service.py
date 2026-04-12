import subprocess
import json
from pathlib import Path
from typing import Optional

from app.models import ProjectState
from app.services.project_store import project_store
from app.utils.logger import get_logger

logger = get_logger(__name__)


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of an audio file in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(audio_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        logger.error(f"Failed to get audio duration: {e}")
        return 0.0


def combine_segment_audio(state: ProjectState) -> Optional[Path]:
    """
    Combine all segment audio files into a single narration track.
    Each segment's audio plays COMPLETELY before the next segment starts.
    This ensures no audio gets cut off mid-sentence.
    """
    if not state.metadata:
        logger.error("No video metadata available")
        return None

    project_dir = project_store.get_project_dir(state.project_id)

    segments_with_audio = [s for s in state.segments if s.audio_path and Path(s.audio_path).exists()]

    if not segments_with_audio:
        logger.warning("No audio segments to combine")
        return None

    logger.info(f"Combining {len(segments_with_audio)} audio segments (sequential, no cutoff)")

    # Save combined audio to output folder
    output_dir = project_dir / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "narration_audio.mp3"

    # Use sequential combination - each audio plays completely before next starts
    return _combine_audio_sequential(state, segments_with_audio, output_path)


def _combine_audio_sequential(
    state: ProjectState,
    segments_with_audio: list,
    output_path: Path
) -> Optional[Path]:
    """
    Combine audio sequentially - each segment's audio plays COMPLETELY.
    Adds silence gaps to roughly align with video segments where possible.
    """
    project_dir = project_store.get_project_dir(state.project_id)

    # Create a concat file
    concat_file = project_dir / "concat_list.txt"
    temp_files = []

    current_time = 0.0

    with open(concat_file, "w") as f:
        for segment in segments_with_audio:
            segment_start = segment.start_time
            segment_duration = segment.end_time - segment.start_time
            audio_duration = get_audio_duration(Path(segment.audio_path))

            logger.info(f"Segment {segment.segment_id}: video={segment_start:.1f}-{segment.end_time:.1f}s ({segment_duration:.1f}s), audio={audio_duration:.1f}s")

            # Add silence before this segment if current_time is behind segment start
            if current_time < segment_start:
                gap = segment_start - current_time
                if gap > 0.05:  # Only add silence if gap is meaningful
                    silence_file = project_dir / f"silence_{segment.segment_id}_pre.wav"
                    _create_silence(gap, silence_file)
                    temp_files.append(silence_file)
                    f.write(f"file '{silence_file}'\n")
                    current_time = segment_start

            # Add the segment's audio (plays COMPLETELY)
            f.write(f"file '{segment.audio_path}'\n")
            current_time += audio_duration

            # If audio was shorter than segment, we could add padding
            # But we DON'T add padding here - we let the next segment's audio
            # start right after this one finishes, even if that means
            # audio is slightly ahead of video

    # Concatenate all files
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"Combined audio saved (sequential): {output_path}")

        # Cleanup temp files
        for tf in temp_files:
            if tf.exists():
                tf.unlink()
        if concat_file.exists():
            concat_file.unlink()

        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"Sequential audio combine failed: {e}")
        return None


def _combine_audio_simple(
    state: ProjectState,
    segments_with_audio: list,
    output_path: Path,
    total_duration: float
) -> Optional[Path]:
    """Simpler fallback method for combining audio."""
    logger.info("Using simple audio combination method")

    project_dir = project_store.get_project_dir(state.project_id)

    # Create a concat file
    concat_file = project_dir / "concat_list.txt"
    temp_files = []

    current_time = 0.0

    with open(concat_file, "w") as f:
        for segment in segments_with_audio:
            # Add silence before this segment if needed
            gap = segment.start_time - current_time
            if gap > 0.1:
                silence_file = project_dir / f"silence_{segment.segment_id}.wav"
                _create_silence(gap, silence_file)
                temp_files.append(silence_file)
                f.write(f"file '{silence_file}'\n")

            f.write(f"file '{segment.audio_path}'\n")

            audio_duration = get_audio_duration(Path(segment.audio_path))
            current_time = segment.start_time + audio_duration

    # Add trailing silence if needed
    if current_time < total_duration:
        silence_file = project_dir / "silence_end.wav"
        _create_silence(total_duration - current_time, silence_file)
        temp_files.append(silence_file)
        with open(concat_file, "a") as f:
            f.write(f"file '{silence_file}'\n")

    # Concatenate all files
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"Combined audio saved (simple method): {output_path}")

        # Cleanup temp files
        for tf in temp_files:
            if tf.exists():
                tf.unlink()
        if concat_file.exists():
            concat_file.unlink()

        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"Simple audio combine failed: {e}")
        return None


def _create_silence(duration: float, output_path: Path) -> bool:
    """Create a silent audio file."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", str(duration),
        "-c:a", "pcm_s16le",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


async def combine_audio_segments(state: ProjectState) -> ProjectState:
    """
    Async wrapper to combine all segment audio files.
    Each segment's narration plays COMPLETELY before the next starts.
    """
    import asyncio

    result_path = await asyncio.to_thread(combine_segment_audio, state)

    if result_path:
        logger.info(f"Audio combination complete: {result_path}")
    else:
        logger.warning("Audio combination returned no output")

    return state


def adjust_audio_speed(audio_path: Path, target_duration: float, output_path: Path) -> bool:
    """Adjust audio speed to match target duration using ffmpeg."""
    current_duration = get_audio_duration(audio_path)

    if current_duration <= 0:
        return False

    speed_factor = current_duration / target_duration

    # atempo filter only accepts 0.5 to 2.0 range
    # For larger changes, chain multiple atempo filters
    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-filter:a", f"atempo={min(max(speed_factor, 0.5), 2.0)}",
        "-c:a", "libmp3lame",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Audio speed adjustment failed: {e}")
        return False
