import shutil
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel

from app.config import settings
from app.models import ProjectResponse, PipelineStep, SegmentAnalysis
from app.services.project_store import project_store
from app.pipeline import run_pipeline, resume_pipeline, restart_from_step
from app.utils.ffmpeg import check_ffmpeg
from app.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info("Starting Auto-Narrated Video Tool")
    if not check_ffmpeg():
        logger.warning("FFmpeg not found! Video processing will fail.")
    yield
    # Shutdown
    logger.info("Shutting down")


app = FastAPI(
    title="Auto-Narrated Video Tool",
    description="Automatically generate voiceover narration for videos",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
static_path = Path(__file__).parent.parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/")
async def root():
    """Serve the web UI."""
    index_path = static_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Auto-Narrated Video Tool API", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "ffmpeg": check_ffmpeg(),
        "vision_backend": settings.vision_backend
    }


@app.get("/voices/preview")
async def preview_voice(voice: str = "en-GB-LibbyNeural"):
    """Generate a voice preview sample."""
    import edge_tts
    import io

    sample_text = "Welcome to the Payments Control Centre. In this demo, we'll show you how refunds work."

    try:
        communicate = edge_tts.Communicate(sample_text, voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]

        from fastapi.responses import Response
        return Response(content=audio_data, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(400, f"Voice preview failed: {e}")


@app.post("/projects/", response_model=ProjectResponse)
async def create_project(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    context: Optional[str] = Form(None),
    voice: Optional[str] = Form("en-GB-LibbyNeural")
):
    """
    Upload a video and start the narration pipeline.
    The pipeline runs in the background - poll /projects/{id} for status.
    """
    # Validate file type
    if not video.filename:
        raise HTTPException(400, "No filename provided")

    suffix = Path(video.filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
        raise HTTPException(400, f"Unsupported video format: {suffix}")

    # Save uploaded file temporarily
    temp_dir = settings.projects_dir / "temp"
    temp_dir.mkdir(exist_ok=True)
    temp_path = temp_dir / video.filename

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(video.file, f)
    except Exception as e:
        raise HTTPException(500, f"Failed to save upload: {e}")

    # Start pipeline in background
    async def run_background():
        try:
            await run_pipeline(temp_path, context)
        finally:
            # Cleanup temp file
            if temp_path.exists():
                temp_path.unlink()

    background_tasks.add_task(run_background)

    # Return immediate response (we need to wait a moment for project creation)
    import asyncio
    from app.services.video_service import ingest_video

    # Do ingestion synchronously to get project ID
    state = await ingest_video(temp_path, context, voice)

    # Continue pipeline in background
    async def continue_bg():
        from app.pipeline import continue_pipeline
        await continue_pipeline(state)

    background_tasks.add_task(continue_bg)

    return ProjectResponse(
        project_id=state.project_id,
        current_step=state.current_step,
        segment_count=len(state.segments),
        output_ready=False
    )


@app.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project_status(project_id: str):
    """Get the current status of a project."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    return ProjectResponse(
        project_id=state.project_id,
        current_step=state.current_step,
        error=state.error,
        segment_count=len(state.segments),
        output_ready=state.output_video is not None and Path(state.output_video).exists()
    )


@app.get("/projects/{project_id}/download")
async def download_output(project_id: str):
    """Download the rendered video."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    if not state.output_video or not Path(state.output_video).exists():
        raise HTTPException(404, "Output video not ready")

    # Get file modification time for cache-busting filename
    output_path = Path(state.output_video)
    mtime = int(output_path.stat().st_mtime)

    response = FileResponse(
        state.output_video,
        media_type="video/mp4",
        filename=f"narrated_{project_id}_{mtime}.mp4"
    )
    # Prevent browser caching
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.post("/projects/{project_id}/resume", response_model=ProjectResponse)
async def resume_project(project_id: str, background_tasks: BackgroundTasks):
    """Resume a failed or paused pipeline."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    background_tasks.add_task(resume_pipeline, project_id)

    return ProjectResponse(
        project_id=state.project_id,
        current_step=state.current_step,
        error=state.error,
        segment_count=len(state.segments),
        output_ready=False
    )


@app.post("/projects/{project_id}/restart-from/{step}", response_model=ProjectResponse)
async def restart_project_from_step(
    project_id: str,
    step: PipelineStep,
    background_tasks: BackgroundTasks
):
    """Restart pipeline from a specific step."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    background_tasks.add_task(restart_from_step, project_id, step)

    return ProjectResponse(
        project_id=state.project_id,
        current_step=step,
        segment_count=len(state.segments),
        output_ready=False
    )


@app.get("/projects/{project_id}/segments")
async def get_segments(project_id: str):
    """Get segment details including narration."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    return {
        "project_id": project_id,
        "segments": [
            {
                "segment_id": s.segment_id,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "description": s.description,
                "narration": s.narration,
                "has_audio": s.audio_path is not None
            }
            for s in state.segments
        ]
    }


@app.get("/projects/")
async def list_projects():
    """List all projects."""
    project_ids = project_store.list_projects()
    projects = []

    for pid in project_ids:
        state = project_store.load_state(pid)
        if state:
            projects.append(ProjectResponse(
                project_id=state.project_id,
                current_step=state.current_step,
                error=state.error,
                segment_count=len(state.segments),
                output_ready=state.output_video is not None
            ))

    return {"projects": projects}


# ============================================================================
# Editor API Endpoints
# ============================================================================

@app.get("/editor/{project_id}")
async def serve_editor(project_id: str):
    """Serve the video editor UI."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    editor_path = static_path / "editor.html"
    if not editor_path.exists():
        raise HTTPException(404, "Editor not found")

    return FileResponse(editor_path)


@app.get("/api/editor/{project_id}")
async def get_editor_data(project_id: str):
    """Get full project data for the editor."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    project_dir = project_store.get_project_dir(project_id)

    # Build segment data with frame paths
    segments_data = []
    for seg in state.segments:
        frame_data = []
        for frame in seg.frames:
            # Return frame data with path and timestamp for the frontend
            frame_data.append({
                "frame_path": frame.frame_path,
                "timestamp": frame.timestamp,
                "ocr_text": frame.ocr_text
            })

        segments_data.append({
            "segment_id": seg.segment_id,
            "start_time": seg.start_time,
            "end_time": seg.end_time,
            "description": seg.description,
            "narration": seg.narration,
            "audio_path": seg.audio_path,
            "frames": frame_data,
            "speed_adjustment": seg.speed_adjustment  # Pre-calculated from AI generation
        })

    # Get video URL
    video_url = None
    video_filename = "video.mp4"
    if state.input_video and Path(state.input_video).exists():
        video_path = Path(state.input_video)
        video_filename = video_path.name

    return {
        "project_id": project_id,
        "current_step": state.current_step,
        "voice": state.voice,
        "context": state.context,
        "video_filename": video_filename,
        "metadata": {
            "duration": state.metadata.duration if state.metadata else 0,
            "width": state.metadata.width if state.metadata else 0,
            "height": state.metadata.height if state.metadata else 0,
            "fps": state.metadata.fps if state.metadata else 0
        },
        "segments": segments_data,
        "output_ready": state.output_video is not None and Path(state.output_video).exists()
    }


# Mount projects directory for serving video/frame files
projects_files_path = settings.projects_dir
app.mount("/projects-files", StaticFiles(directory=str(projects_files_path)), name="projects-files")


class UpdateSegmentRequest(BaseModel):
    narration: str


@app.patch("/api/editor/{project_id}/segments/{segment_idx}")
async def update_segment_narration(project_id: str, segment_idx: int, request: UpdateSegmentRequest):
    """Update narration text for a segment."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    if segment_idx < 0 or segment_idx >= len(state.segments):
        raise HTTPException(400, f"Invalid segment index: {segment_idx}")

    # Update the segment's narration
    updated_segments = []
    for i, seg in enumerate(state.segments):
        if i == segment_idx:
            updated_seg = seg.model_copy(update={"narration": request.narration})
            updated_segments.append(updated_seg)
        else:
            updated_segments.append(seg)

    state = state.model_copy(update={"segments": updated_segments})
    project_store.save_state(state)

    return {"success": True, "segment_id": segment_idx, "narration": request.narration}


class PreviewAudioRequest(BaseModel):
    text: str
    voice: str = "en-GB-LibbyNeural"


@app.post("/api/editor/preview-audio")
async def preview_segment_audio(request: PreviewAudioRequest):
    """Generate audio preview for given text."""
    import edge_tts

    if not request.text.strip():
        raise HTTPException(400, "Text cannot be empty")

    try:
        communicate = edge_tts.Communicate(request.text, request.voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]

        from fastapi.responses import Response
        return Response(content=audio_data, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(400, f"Audio preview failed: {e}")


@app.post("/api/editor/{project_id}/segments/{segment_idx}/regenerate")
async def regenerate_segment_audio(project_id: str, segment_idx: int):
    """Regenerate audio for a specific segment using its current narration."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    if segment_idx < 0 or segment_idx >= len(state.segments):
        raise HTTPException(400, f"Invalid segment index: {segment_idx}")

    segment = state.segments[segment_idx]
    if not segment.narration or not segment.narration.strip():
        raise HTTPException(400, "Segment has no narration text")

    # Generate new audio
    from app.services.tts_service import synthesize_speech

    project_dir = project_store.get_project_dir(project_id)
    audio_dir = project_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    audio_path = audio_dir / f"segment_{segment.segment_id:03d}.mp3"

    success = await synthesize_speech(
        text=segment.narration,
        output_path=audio_path,
        voice=state.voice
    )

    if not success:
        raise HTTPException(500, "Failed to generate audio")

    # Update segment with new audio path
    updated_segments = []
    for i, seg in enumerate(state.segments):
        if i == segment_idx:
            updated_seg = seg.model_copy(update={"audio_path": str(audio_path)})
            updated_segments.append(updated_seg)
        else:
            updated_segments.append(seg)

    state = state.model_copy(update={"segments": updated_segments})
    project_store.save_state(state)

    return {"success": True, "segment_id": segment_idx, "audio_path": str(audio_path)}


class UpdateVoiceRequest(BaseModel):
    voice: str


@app.patch("/api/editor/{project_id}/voice")
async def update_project_voice(project_id: str, request: UpdateVoiceRequest):
    """Update the voice setting for a project."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    state = state.model_copy(update={"voice": request.voice})
    project_store.save_state(state)

    return {"success": True, "voice": request.voice}


@app.post("/api/editor/{project_id}/regenerate-all-audio")
async def regenerate_all_audio(project_id: str, background_tasks: BackgroundTasks):
    """Regenerate audio for all segments."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    async def regen_all():
        from app.services.tts_service import synthesize_all_segments
        await synthesize_all_segments(state)

    background_tasks.add_task(regen_all)

    return {"success": True, "message": "Audio regeneration started"}


class RenderRequest(BaseModel):
    voice: str = "en-GB-LibbyNeural"
    speed_adjustments: dict = {}
    freeze_frames: bool = True  # Freeze last frame when narration extends beyond video segment


@app.post("/api/editor/{project_id}/render")
async def render_video(project_id: str, request: RenderRequest, background_tasks: BackgroundTasks):
    """Re-render the final video with current segments.

    This regenerates audio for ALL segments using current narration text,
    then combines and renders the final video.
    Supports per-segment speed adjustments for longer narrations.
    """
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    # Check all segments have narration text
    missing_narration = [s.segment_id for s in state.segments if not s.narration or not s.narration.strip()]
    if missing_narration:
        raise HTTPException(400, f"Segments missing narration: {missing_narration}")

    speed_adjustments = request.speed_adjustments

    async def do_render():
        from app.services.tts_service import synthesize_all_segments
        from app.utils.ffmpeg import render_preview_style, render_with_speed_adjustments, render_with_freeze_frames

        # Reload state to get latest changes
        current_state = project_store.load_state(project_id)

        # Update voice from request (ensures we use the voice user selected)
        if request.voice:
            logger.info(f"Using voice from render request: {request.voice}")
            current_state = current_state.model_copy(update={"voice": request.voice})
            project_store.save_state(current_state)

        # Step 1: Regenerate audio for ALL segments with current narration text and selected voice
        logger.info(f"Regenerating audio for all segments with voice: {current_state.voice}")
        current_state = await synthesize_all_segments(current_state)

        # Step 2: Render final video - preview style (audio at segment start times)
        # This matches exactly what users hear during preview playback
        logger.info(f"Rendering final video preview-style (speed adjustments: {speed_adjustments})")

        project_dir = project_store.get_project_dir(project_id)
        video_path = Path(current_state.input_video)
        output_path = project_dir / "output" / "narrated_video.mp4"

        if speed_adjustments:
            # Use speed adjustment rendering for segments that need slowing
            from app.services.audio_service import combine_audio_segments
            current_state = await combine_audio_segments(current_state)
            audio_path = project_dir / "output" / "narration_audio.mp3"
            success = render_with_speed_adjustments(
                video_path=video_path,
                audio_path=audio_path,
                output_path=output_path,
                segments=current_state.segments,
                speed_adjustments=speed_adjustments
            )
        else:
            if request.freeze_frames:
                # Freeze-frame render - extends video with frozen frame when narration is longer
                logger.info("Using freeze-frame render for extended narration")
                success = render_with_freeze_frames(
                    video_path=video_path,
                    segments=current_state.segments,
                    output_path=output_path
                )
            else:
                # Preview-style render - each audio plays at its segment start time
                success = render_preview_style(
                    video_path=video_path,
                    segments=current_state.segments,
                    output_path=output_path
                )

        if success:
            current_state = current_state.model_copy(update={
                "current_step": PipelineStep.COMPLETED,
                "output_video": str(output_path)
            })
        else:
            current_state = current_state.model_copy(update={
                "current_step": PipelineStep.FAILED,
                "error": "Video rendering failed"
            })

        project_store.save_state(current_state)
        logger.info("Render complete")

    background_tasks.add_task(do_render)

    return {"success": True, "message": "Regenerating audio and rendering video..."}


@app.post("/api/editor/{project_id}/regenerate-narrations")
async def regenerate_all_narrations(project_id: str, background_tasks: BackgroundTasks):
    """Regenerate narration text for all segments using AI."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    async def regen_narrations():
        from app.services.narration_service import generate_narration
        await generate_narration(state)

    background_tasks.add_task(regen_narrations)

    return {"success": True, "message": "Narration regeneration started"}


@app.post("/api/editor/{project_id}/regenerate-all")
async def regenerate_all(project_id: str, background_tasks: BackgroundTasks):
    """Regenerate all narrations and audio for all segments."""
    state = project_store.load_state(project_id)
    if not state:
        raise HTTPException(404, "Project not found")

    async def regen_all():
        from app.services.narration_service import generate_narration
        from app.services.tts_service import synthesize_all_segments

        # First regenerate narrations
        updated_state = await generate_narration(state)
        # Then regenerate audio
        await synthesize_all_segments(updated_state)

    background_tasks.add_task(regen_all)

    return {"success": True, "message": "Full regeneration started"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
