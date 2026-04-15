import subprocess
import json
from pathlib import Path
from typing import Optional
from app.models import VideoMetadata
from app.utils.logger import get_logger

logger = get_logger(__name__)


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_video_metadata(video_path: Path) -> VideoMetadata:
    """Extract metadata from video using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    # Find video stream
    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise ValueError("No video stream found")

    # Parse FPS (can be fraction like "30000/1001")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fps_str)

    return VideoMetadata(
        duration=float(data["format"]["duration"]),
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=round(fps, 2),
        codec=video_stream.get("codec_name", "unknown"),
        file_size=int(data["format"]["size"])
    )


def extract_frame(video_path: Path, timestamp: float, output_path: Path) -> bool:
    """Extract a single frame at the given timestamp."""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path.exists()
    except subprocess.CalledProcessError as e:
        logger.error(f"Frame extraction failed: {e}")
        return False


def render_with_freeze_frames(
    video_path: Path,
    segments: list,
    output_path: Path,
    original_audio_volume: float = 0.05,
    narration_volume: float = 2.5
) -> bool:
    """
    Render video with freeze-frame effect when narration extends beyond video segment.
    If narration is longer than the video segment, the last frame freezes until narration completes.
    """
    import shutil

    logger.info("Rendering with freeze-frames for extended narration")

    video_path = Path(video_path).resolve()
    output_path = Path(output_path).resolve()

    temp_dir = output_path.parent / "temp_freeze"
    temp_dir.mkdir(exist_ok=True)

    try:
        # Get segments with audio and their durations
        segments_with_audio = []
        for s in segments:
            if s.audio_path and Path(s.audio_path).exists():
                dur_cmd = [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(s.audio_path)
                ]
                dur_result = subprocess.run(dur_cmd, capture_output=True, text=True)
                audio_dur = float(dur_result.stdout.strip()) if dur_result.stdout.strip() else 0
                segments_with_audio.append((s, audio_dur))

        if not segments_with_audio:
            logger.warning("No segments with audio found")
            return False

        # Get video properties for consistent freeze frame creation
        meta = get_video_metadata(video_path)
        video_width = meta.width
        video_height = meta.height
        video_fps = meta.fps
        logger.info(f"Video properties: {video_width}x{video_height} @ {video_fps}fps")

        # Calculate original video duration for comparison
        original_total = sum(s.end_time - s.start_time for s, _ in segments_with_audio)
        logger.info(f"Original video segments total: {original_total:.1f}s")

        # Process each segment - extend with freeze frame if needed
        segment_videos = []
        segment_durations = []  # Track extended duration of each segment

        for i, (seg, audio_dur) in enumerate(segments_with_audio):
            seg_video = temp_dir / f"seg_{i:03d}.mp4"
            video_start = seg.start_time
            video_end = seg.end_time
            video_dur = video_end - video_start

            # Simple: if audio is longer than video segment, freeze the difference
            freeze_duration = max(0, audio_dur - video_dur)
            extended_duration = video_dur + freeze_duration
            segment_durations.append(extended_duration)

            logger.info(f"Segment {seg.segment_id}: video {video_dur:.1f}s, audio {audio_dur:.1f}s, freeze {freeze_duration:.1f}s, total {extended_duration:.1f}s")

            if freeze_duration > 0.1:
                # Need to extend with freeze frame
                # Extract segment with consistent encoding
                seg_normal = temp_dir / f"seg_{i:03d}_normal.mp4"
                cmd1 = [
                    "ffmpeg", "-y",
                    "-ss", str(video_start),
                    "-t", str(video_dur),
                    "-i", str(video_path),
                    "-c:v", "libx264", "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    "-r", str(video_fps),
                    "-an",
                    str(seg_normal)
                ]
                result1 = subprocess.run(cmd1, capture_output=True)
                if result1.returncode != 0:
                    logger.error(f"Segment {i} normal extraction failed: {result1.stderr.decode()[:200]}")

                # Extract the last frame as PNG (better quality for re-encoding)
                last_frame = temp_dir / f"seg_{i:03d}_last.png"
                cmd2 = [
                    "ffmpeg", "-y",
                    "-ss", str(video_end - 0.1),
                    "-i", str(video_path),
                    "-frames:v", "1",
                    str(last_frame)
                ]
                result2 = subprocess.run(cmd2, capture_output=True)
                if result2.returncode != 0:
                    logger.error(f"Segment {i} frame extraction failed: {result2.stderr.decode()[:200]}")

                # Create freeze frame video with EXACT same properties as segment
                seg_freeze = temp_dir / f"seg_{i:03d}_freeze.mp4"
                cmd3 = [
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-i", str(last_frame),
                    "-t", str(freeze_duration),
                    "-vf", f"scale={video_width}:{video_height}:force_original_aspect_ratio=decrease,pad={video_width}:{video_height}:(ow-iw)/2:(oh-ih)/2",
                    "-c:v", "libx264", "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    "-r", str(video_fps),
                    str(seg_freeze)
                ]
                result3 = subprocess.run(cmd3, capture_output=True)
                if result3.returncode != 0:
                    logger.error(f"Segment {i} freeze creation failed: {result3.stderr.decode()[:200]}")

                # Check both files exist before concat
                if not seg_normal.exists() or not seg_freeze.exists():
                    logger.error(f"Segment {i}: Missing files for concat (normal={seg_normal.exists()}, freeze={seg_freeze.exists()})")
                    # Fallback: just use the normal segment
                    if seg_normal.exists():
                        import shutil as sh
                        sh.copy(seg_normal, seg_video)
                    continue

                # Concatenate using filter_complex for reliability
                cmd4 = [
                    "ffmpeg", "-y",
                    "-i", str(seg_normal),
                    "-i", str(seg_freeze),
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[outv]",
                    "-map", "[outv]",
                    "-c:v", "libx264", "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    str(seg_video)
                ]
                result4 = subprocess.run(cmd4, capture_output=True)
                if result4.returncode != 0:
                    logger.error(f"Segment {i} concat failed: {result4.stderr.decode()[:200]}")
                    # Fallback: just use normal segment
                    if seg_normal.exists():
                        import shutil as sh
                        sh.copy(seg_normal, seg_video)
                else:
                    logger.info(f"Segment {i}: Created extended video with {freeze_duration:.1f}s freeze")
            else:
                # No freeze needed, just extract segment
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(video_start),
                    "-t", str(video_dur),
                    "-i", str(video_path),
                    "-c:v", "libx264", "-preset", "fast",
                    "-an",
                    str(seg_video)
                ]
                subprocess.run(cmd, capture_output=True)

            segment_videos.append(seg_video)

        # Log total extended duration
        extended_total = sum(segment_durations)
        logger.info(f"Extended video segments total: {extended_total:.1f}s (added {extended_total - original_total:.1f}s freeze time)")

        # Concatenate all segment videos
        final_concat = temp_dir / "final_concat.txt"
        with open(final_concat, "w") as f:
            for sv in segment_videos:
                f.write(f"file '{sv.resolve()}'\n")

        concat_video = temp_dir / "concat_video.mp4"
        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(final_concat),
            "-c:v", "libx264", "-preset", "fast",
            str(concat_video)
        ]
        subprocess.run(cmd_concat, capture_output=True)

        # Get the new video duration
        dur_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(concat_video)
        ]
        dur_result = subprocess.run(dur_cmd, capture_output=True, text=True)
        new_video_duration = float(dur_result.stdout.strip()) if dur_result.stdout.strip() else 60.0
        logger.info(f"Extended video duration: {new_video_duration:.1f}s")

        # Now add audio with proper timing based on EXTENDED video durations
        cmd_audio = ["ffmpeg", "-y", "-i", str(concat_video)]

        for seg, _ in segments_with_audio:
            cmd_audio.extend(["-i", str(Path(seg.audio_path).resolve())])

        # Build filter complex - audio starts at cumulative extended segment positions
        filter_parts = []
        num_audios = len(segments_with_audio)

        # Calculate cumulative start times based on extended segment durations
        cumulative_time = 0.0
        for i, (seg, audio_dur) in enumerate(segments_with_audio):
            # Each audio starts at the beginning of its segment in the EXTENDED video
            delay_ms = int(cumulative_time * 1000)
            filter_parts.append(f"[{i+1}:a]adelay={delay_ms}|{delay_ms},volume={narration_volume}[a{i}]")
            logger.info(f"Audio {i}: delay={delay_ms}ms, duration={audio_dur:.1f}s")
            # Move to start of next segment using extended duration
            cumulative_time += segment_durations[i]

        audio_inputs = "".join(f"[a{i}]" for i in range(num_audios))
        filter_parts.append(f"{audio_inputs}amix=inputs={num_audios}:duration=longest:normalize=0[narration]")

        filter_complex = ";".join(filter_parts)

        cmd_audio.extend([
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[narration]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(new_video_duration),
            str(output_path)
        ])

        logger.info(f"Adding audio to extended video")
        result = subprocess.run(cmd_audio, capture_output=True)

        if result.returncode != 0:
            logger.error(f"Audio mixing failed: {result.stderr.decode()[:500]}")
            return False

        logger.info(f"Freeze-frame render complete: {output_path}")
        return output_path.exists()

    except Exception as e:
        logger.error(f"Freeze-frame render error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


def render_preview_style(
    video_path: Path,
    segments: list,
    output_path: Path,
    original_audio_volume: float = 0.05,
    narration_volume: float = 2.5
) -> bool:
    """
    Render video exactly like preview - each segment's audio plays SEQUENTIALLY.
    Audio for segment N must finish before audio for segment N+1 starts.
    This matches the preview playback behavior exactly.
    """
    logger.info("Rendering preview-style (sequential audio, no overlap)")

    # Get video duration
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(video_path)
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    video_duration = float(probe_result.stdout.strip()) if probe_result.stdout.strip() else 60.0

    # Check if input video has audio
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        str(video_path)
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    has_video_audio = bool(probe_result.stdout.strip())

    # Get segments with audio and their durations
    segments_with_audio = []
    for s in segments:
        if s.audio_path and Path(s.audio_path).exists():
            # Get audio duration
            dur_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(s.audio_path)
            ]
            dur_result = subprocess.run(dur_cmd, capture_output=True, text=True)
            audio_dur = float(dur_result.stdout.strip()) if dur_result.stdout.strip() else 0
            segments_with_audio.append((s, audio_dur))

    if not segments_with_audio:
        logger.warning("No segments with audio found")
        return False

    try:
        # Calculate actual start times for sequential playback (like preview)
        # Each audio starts when the previous one finishes, but not before its segment start time
        actual_start_times = []
        current_time = 0.0

        for seg, audio_dur in segments_with_audio:
            # Start at segment start time, or when previous audio finishes (whichever is later)
            start_time = max(seg.start_time, current_time)
            actual_start_times.append(start_time)
            current_time = start_time + audio_dur
            logger.info(f"Segment {seg.segment_id}: starts at {start_time:.2f}s, duration {audio_dur:.2f}s, ends at {current_time:.2f}s")

        # Build ffmpeg command with all audio inputs
        cmd = ["ffmpeg", "-y", "-i", str(video_path)]

        # Add each segment audio as input
        for seg, _ in segments_with_audio:
            cmd.extend(["-i", seg.audio_path])

        # Build filter complex with calculated start times
        filter_parts = []
        num_audios = len(segments_with_audio)

        for i, ((seg, _), start_time) in enumerate(zip(segments_with_audio, actual_start_times)):
            delay_ms = int(start_time * 1000)
            # Input index is i+1 (0 is video)
            filter_parts.append(f"[{i+1}:a]adelay={delay_ms}|{delay_ms},volume={narration_volume}[a{i}]")

        # Mix all delayed audios together (use longest to capture all audio, then trim with -t)
        audio_inputs = "".join(f"[a{i}]" for i in range(num_audios))
        filter_parts.append(f"{audio_inputs}amix=inputs={num_audios}:duration=longest:normalize=0[narration]")

        # If video has audio, mix it with narration
        if has_video_audio:
            filter_parts.append(f"[0:a]volume={original_audio_volume}[orig]")
            filter_parts.append(f"[orig][narration]amix=inputs=2:duration=longest:normalize=0[final]")
            final_audio = "[final]"
        else:
            final_audio = "[narration]"

        filter_complex = ";".join(filter_parts)

        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", final_audio,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(video_duration),
            str(output_path)
        ])

        logger.info(f"Running preview-style render with {num_audios} audio segments (sequential)")
        result = subprocess.run(cmd, capture_output=True)

        if result.returncode != 0:
            logger.error(f"Preview-style render failed: {result.stderr.decode()}")
            return False

        return output_path.exists()

    except Exception as e:
        logger.error(f"Preview-style render error: {e}")
        return False


def render_final_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    original_audio_volume: float = 0.05,
    narration_volume: float = 2.5,
    high_quality: bool = True
) -> bool:
    """Merge video with narration audio.

    Args:
        high_quality: If True, re-encode video with high quality settings.
                     If False, copy video stream (faster but same quality).
    """
    # Check if input video has audio
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        str(video_path)
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    has_audio = bool(probe_result.stdout.strip())

    # Video encoding settings for high quality
    if high_quality:
        video_codec = [
            "-c:v", "libx264",
            "-preset", "slow",        # Better compression, slower encoding
            "-crf", "18",             # High quality (18-23 is good, lower = better)
            "-pix_fmt", "yuv420p",    # Compatibility
            "-movflags", "+faststart" # Web optimization
        ]
    else:
        video_codec = ["-c:v", "copy"]

    # Audio settings - high quality AAC
    audio_codec = [
        "-c:a", "aac",
        "-b:a", "256k",   # Higher bitrate for better audio
        "-ar", "48000"    # 48kHz sample rate
    ]

    try:
        if has_audio:
            # Mix original audio with narration
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-filter_complex",
                f"[0:a]volume={original_audio_volume}[oa];[1:a]volume={narration_volume}[na];[oa][na]amix=inputs=2:duration=longest:normalize=0[a]",
                "-map", "0:v",
                "-map", "[a]",
                *video_codec,
                *audio_codec,
                str(output_path)
            ]
        else:
            # Video has no audio, just add narration
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-map", "0:v",
                "-map", "1:a",
                *video_codec,
                *audio_codec,
                "-shortest",
                str(output_path)
            ]

        logger.info(f"Rendering video with {'high' if high_quality else 'fast'} quality settings")
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path.exists()
    except subprocess.CalledProcessError as e:
        logger.error(f"Video rendering failed: {e.stderr.decode() if e.stderr else e}")
        return False


def create_silent_audio(duration: float, output_path: Path, sample_rate: int = 44100) -> bool:
    """Create a silent audio file of specified duration."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r={sample_rate}:cl=stereo",
        "-t", str(duration),
        "-c:a", "pcm_s16le",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path.exists()
    except subprocess.CalledProcessError as e:
        logger.error(f"Silent audio creation failed: {e}")
        return False


def render_with_speed_adjustments(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    segments: list,
    speed_adjustments: dict,
    original_audio_volume: float = 0.05,
    narration_volume: float = 2.5,
    transition_duration: float = 0.3
) -> bool:
    """
    Render video with per-segment speed adjustments and smooth transitions.

    For segments that need slowing down:
    1. Extract segment
    2. Apply speed filter
    3. Add fade transitions between segments
    4. Concatenate all segments
    5. Add narration audio
    """
    if not speed_adjustments:
        # No speed adjustments, use normal render with transitions
        return render_with_transitions(video_path, audio_path, output_path,
                                       segments, original_audio_volume,
                                       narration_volume, transition_duration)

    logger.info(f"Rendering with speed adjustments: {speed_adjustments}")

    # Check if input video has audio
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        str(video_path)
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    has_audio = bool(probe_result.stdout.strip())

    temp_dir = output_path.parent / "temp_segments"
    temp_dir.mkdir(exist_ok=True)

    try:
        segment_files = []
        num_segments = len(segments)

        for i, seg in enumerate(segments):
            seg_output = temp_dir / f"seg_{i:03d}.mp4"
            start = seg.start_time
            duration = seg.end_time - seg.start_time

            # Check if this segment needs speed adjustment
            speed = speed_adjustments.get(str(i), 1.0)

            # Build video filter with speed and fade transitions
            video_filters = []
            audio_filters = []

            if speed < 1.0:
                video_filters.append(f"setpts=PTS/{speed}")
                audio_filters.append(f"atempo={speed}")
                # Output duration will be longer after slowdown
                output_duration = duration / speed
                logger.info(f"Segment {i}: slowing from {duration:.2f}s to {output_duration:.2f}s (speed={speed})")
            else:
                output_duration = duration

            # Add fade in for all segments except first
            if i > 0:
                video_filters.append(f"fade=t=in:st=0:d={transition_duration}")
                audio_filters.append(f"afade=t=in:st=0:d={transition_duration}")

            # Add fade out for all segments except last
            if i < num_segments - 1:
                fade_start = max(0, output_duration - transition_duration)
                video_filters.append(f"fade=t=out:st={fade_start}:d={transition_duration}")
                audio_filters.append(f"afade=t=out:st={fade_start}:d={transition_duration}")

            # Build filter string
            if video_filters or (audio_filters and has_audio):
                v_filter = ",".join(video_filters) if video_filters else "null"

                if has_audio and audio_filters:
                    a_filter = ",".join(audio_filters)
                    filter_complex = f"[0:v]{v_filter}[v];[0:a]{a_filter}[a]"
                    map_args = ["-map", "[v]", "-map", "[a]"]
                    audio_codec = ["-c:a", "aac", "-b:a", "192k"]
                else:
                    filter_complex = f"[0:v]{v_filter}[v]"
                    map_args = ["-map", "[v]"]
                    audio_codec = []

                # Note: We use input duration (-t before -i for input trimming)
                # The output will be longer due to speed adjustment
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start),
                    "-t", str(duration),  # Input duration (before slowdown)
                    "-i", str(video_path),
                    "-filter_complex", filter_complex,
                    *map_args,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    *audio_codec,
                    str(seg_output)
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start),
                    "-t", str(duration),
                    "-i", str(video_path),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k",
                    str(seg_output)
                ]

            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                logger.error(f"Segment {i} extraction failed: {result.stderr.decode()}")
                return False

            segment_files.append(seg_output)

        # Create concat file
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for seg_file in segment_files:
                f.write(f"file '{seg_file}'\n")

        # Concatenate all segments
        concat_output = temp_dir / "concatenated.mp4"
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(concat_output)
        ]

        result = subprocess.run(concat_cmd, capture_output=True)
        if result.returncode != 0:
            logger.error(f"Concatenation failed: {result.stderr.decode()}")
            return False

        # Now add narration audio to concatenated video
        success = render_final_video(
            concat_output, audio_path, output_path,
            original_audio_volume, narration_volume, high_quality=True
        )

        return success

    except Exception as e:
        logger.error(f"Speed-adjusted render failed: {e}")
        return False
    finally:
        # Cleanup temp files
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


def render_with_transitions(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    segments: list,
    original_audio_volume: float = 0.05,
    narration_volume: float = 2.5,
    transition_duration: float = 0.3
) -> bool:
    """
    Render video with smooth fade transitions between segments.
    No speed adjustments, just transitions for a polished look.
    """
    logger.info(f"Rendering with {transition_duration}s fade transitions")

    # Check if input video has audio
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        str(video_path)
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    has_audio = bool(probe_result.stdout.strip())

    temp_dir = output_path.parent / "temp_segments"
    temp_dir.mkdir(exist_ok=True)

    try:
        segment_files = []
        num_segments = len(segments)

        for i, seg in enumerate(segments):
            seg_output = temp_dir / f"seg_{i:03d}.mp4"
            start = seg.start_time
            duration = seg.end_time - seg.start_time

            video_filters = []
            audio_filters = []

            # Add fade in for all segments except first
            if i > 0:
                video_filters.append(f"fade=t=in:st=0:d={transition_duration}")
                if has_audio:
                    audio_filters.append(f"afade=t=in:st=0:d={transition_duration}")

            # Add fade out for all segments except last
            if i < num_segments - 1:
                fade_start = max(0, duration - transition_duration)
                video_filters.append(f"fade=t=out:st={fade_start}:d={transition_duration}")
                if has_audio:
                    audio_filters.append(f"afade=t=out:st={fade_start}:d={transition_duration}")

            if video_filters:
                v_filter = ",".join(video_filters)

                if has_audio and audio_filters:
                    a_filter = ",".join(audio_filters)
                    filter_complex = f"[0:v]{v_filter}[v];[0:a]{a_filter}[a]"
                    map_args = ["-map", "[v]", "-map", "[a]"]
                else:
                    filter_complex = f"[0:v]{v_filter}[v]"
                    map_args = ["-map", "[v]"]

                audio_codec = ["-c:a", "aac", "-b:a", "192k"] if has_audio else []
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start),
                    "-i", str(video_path),
                    "-t", str(duration),
                    "-filter_complex", filter_complex,
                    *map_args,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    *audio_codec,
                    str(seg_output)
                ]
            else:
                # First and only segment - no transitions needed
                audio_codec = ["-c:a", "aac", "-b:a", "192k"] if has_audio else []
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start),
                    "-i", str(video_path),
                    "-t", str(duration),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    *audio_codec,
                    str(seg_output)
                ]

            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                logger.error(f"Segment {i} extraction failed: {result.stderr.decode()}")
                # Fall back to simple render without transitions
                logger.info("Falling back to render without transitions")
                return render_final_video(video_path, audio_path, output_path,
                                         original_audio_volume, narration_volume)

            segment_files.append(seg_output)

        # Create concat file
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for seg_file in segment_files:
                f.write(f"file '{seg_file}'\n")

        # Concatenate all segments
        concat_output = temp_dir / "concatenated.mp4"
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(concat_output)
        ]

        result = subprocess.run(concat_cmd, capture_output=True)
        if result.returncode != 0:
            logger.error(f"Concatenation failed: {result.stderr.decode()}")
            return render_final_video(video_path, audio_path, output_path,
                                     original_audio_volume, narration_volume)

        # Add narration audio to concatenated video
        success = render_final_video(
            concat_output, audio_path, output_path,
            original_audio_volume, narration_volume, high_quality=True
        )

        return success

    except Exception as e:
        logger.error(f"Transition render failed: {e}")
        return render_final_video(video_path, audio_path, output_path,
                                 original_audio_volume, narration_volume)
    finally:
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
