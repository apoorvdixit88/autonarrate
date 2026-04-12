from pathlib import Path
from typing import Optional

from app.models import ProjectState, PipelineStep
from app.services.project_store import project_store
from app.services.video_service import ingest_video
from app.services.scene_service import segment_video
from app.services.vision_service import analyze_segments
from app.services.narration_service import generate_narration_script
from app.services.tts_service import synthesize_all_segments
from app.services.render_service import render_video
from app.utils.logger import get_logger

logger = get_logger(__name__)


PIPELINE_STEPS = [
    (PipelineStep.INGESTING, None),  # Handled separately
    (PipelineStep.SEGMENTING, segment_video),
    (PipelineStep.EXTRACTING_FRAMES, None),  # Part of segmenting
    (PipelineStep.ANALYZING_FRAMES, analyze_segments),
    (PipelineStep.GENERATING_SCRIPT, generate_narration_script),
    (PipelineStep.SYNTHESIZING_AUDIO, synthesize_all_segments),
    (PipelineStep.RENDERING, render_video),
]


async def run_pipeline(
    video_path: Path,
    context: Optional[str] = None
) -> ProjectState:
    """Run the complete pipeline on a video."""
    logger.info(f"Starting pipeline for {video_path}")

    # Step 1: Ingest
    state = await ingest_video(video_path, context)
    logger.info(f"Project created: {state.project_id}")

    # Run remaining steps
    state = await continue_pipeline(state)

    return state


async def continue_pipeline(state: ProjectState) -> ProjectState:
    """Continue pipeline from current state."""
    try:
        # Step 2: Segment and extract frames
        if state.current_step in [PipelineStep.INGESTING, PipelineStep.PENDING]:
            state = await segment_video(state)

        # Step 3: Analyze frames with vision
        if state.current_step == PipelineStep.EXTRACTING_FRAMES:
            state = await analyze_segments(state)

        # Step 4: Generate narration script
        if state.current_step == PipelineStep.ANALYZING_FRAMES:
            state = await generate_narration_script(state)

        # Step 5: Synthesize audio
        if state.current_step == PipelineStep.GENERATING_SCRIPT:
            state = await synthesize_all_segments(state)

        # Step 6: Render final video
        if state.current_step == PipelineStep.SYNTHESIZING_AUDIO:
            state = await render_video(state)

        logger.info(f"Pipeline completed with status: {state.current_step}")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        state = state.model_copy(update={
            "current_step": PipelineStep.FAILED,
            "error": str(e)
        })
        project_store.save_state(state)

    return state


async def resume_pipeline(project_id: str) -> ProjectState:
    """Resume a pipeline from its last saved state."""
    state = project_store.load_state(project_id)
    if not state:
        raise ValueError(f"Project not found: {project_id}")

    if state.current_step == PipelineStep.COMPLETED:
        logger.info("Pipeline already completed")
        return state

    if state.current_step == PipelineStep.FAILED:
        # Reset error and try to continue
        state = state.model_copy(update={"error": None})

    return await continue_pipeline(state)


async def restart_from_step(project_id: str, step: PipelineStep) -> ProjectState:
    """Restart pipeline from a specific step."""
    state = project_store.load_state(project_id)
    if not state:
        raise ValueError(f"Project not found: {project_id}")

    # Map step to the appropriate starting point
    step_order = [
        PipelineStep.SEGMENTING,
        PipelineStep.EXTRACTING_FRAMES,
        PipelineStep.ANALYZING_FRAMES,
        PipelineStep.GENERATING_SCRIPT,
        PipelineStep.SYNTHESIZING_AUDIO,
        PipelineStep.RENDERING,
    ]

    if step not in step_order:
        raise ValueError(f"Cannot restart from step: {step}")

    # Set state to just before the requested step
    step_index = step_order.index(step)
    if step_index > 0:
        state = state.model_copy(update={
            "current_step": step_order[step_index - 1],
            "error": None
        })
    else:
        state = state.model_copy(update={
            "current_step": PipelineStep.INGESTING,
            "error": None
        })

    project_store.save_state(state)
    return await continue_pipeline(state)
