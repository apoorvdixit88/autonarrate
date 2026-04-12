from pathlib import Path

from app.models import ProjectState, PipelineStep
from app.services.project_store import project_store
from app.services.audio_service import combine_segment_audio
from app.utils.ffmpeg import render_final_video
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def render_video(state: ProjectState) -> ProjectState:
    """
    Render the final video with narration audio.

    1. Combine all segment audio into single track
    2. Merge with original video
    3. Output final MP4
    """
    logger.info("Rendering final video")

    state = state.model_copy(update={"current_step": PipelineStep.RENDERING})
    project_store.save_state(state)

    project_dir = project_store.get_project_dir(state.project_id)
    video_path = Path(state.input_video)

    # Combine segment audio
    combined_audio = combine_segment_audio(state)

    if not combined_audio:
        logger.error("Failed to combine audio segments")
        state = state.model_copy(update={
            "current_step": PipelineStep.FAILED,
            "error": "Failed to combine audio segments"
        })
        project_store.save_state(state)
        return state

    # Render final video to output folder
    output_dir = project_dir / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "narrated_video.mp4"

    success = render_final_video(
        video_path=video_path,
        audio_path=combined_audio,
        output_path=output_path,
        original_audio_volume=0.1  # Keep original audio quiet
    )

    if success:
        state = state.model_copy(update={
            "current_step": PipelineStep.COMPLETED,
            "output_video": str(output_path)
        })
        logger.info(f"Video rendered successfully: {output_path}")
    else:
        state = state.model_copy(update={
            "current_step": PipelineStep.FAILED,
            "error": "Video rendering failed"
        })
        logger.error("Video rendering failed")

    project_store.save_state(state)
    return state
