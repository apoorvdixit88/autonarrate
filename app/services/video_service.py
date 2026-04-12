import shutil
from pathlib import Path
from typing import Optional
import uuid

from app.models import ProjectState, VideoMetadata, PipelineStep
from app.services.project_store import project_store
from app.utils.ffmpeg import get_video_metadata
from app.utils.logger import get_logger

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def validate_video(file_path: Path) -> bool:
    """Validate that the file is a supported video format."""
    return file_path.suffix.lower() in ALLOWED_EXTENSIONS


async def ingest_video(
    video_path: Path,
    context: Optional[str] = None,
    voice: str = "en-GB-LibbyNeural"
) -> ProjectState:
    """
    Ingest a video file and create a new project.

    1. Validate the video
    2. Create project directory
    3. Copy video to project
    4. Extract metadata
    5. Return initial project state
    """
    # Validate
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if not validate_video(video_path):
        raise ValueError(f"Unsupported video format: {video_path.suffix}")

    # Generate project ID
    project_id = str(uuid.uuid4())[:8]
    logger.info(f"Ingesting video for project {project_id}: {video_path}")

    # Create project with organized folder structure
    project_dir = project_store.get_project_dir(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "input").mkdir(exist_ok=True)
    (project_dir / "output").mkdir(exist_ok=True)
    (project_dir / "frames").mkdir(exist_ok=True)
    (project_dir / "audio").mkdir(exist_ok=True)

    # Copy video to input folder
    dest_video = project_dir / "input" / f"video{video_path.suffix}"
    shutil.copy2(video_path, dest_video)

    # Extract metadata
    metadata = get_video_metadata(dest_video)
    logger.info(f"Video metadata: {metadata.duration:.1f}s, {metadata.width}x{metadata.height}, {metadata.fps}fps")

    # Create initial state
    state = ProjectState(
        project_id=project_id,
        input_video=str(dest_video),
        context=context,
        voice=voice,
        current_step=PipelineStep.INGESTING,
        metadata=metadata
    )

    project_store.save_state(state)

    return state
