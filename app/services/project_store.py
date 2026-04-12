import json
from pathlib import Path
from typing import Optional
from app.models import ProjectState, PipelineStep
from app.config import settings
from app.utils.logger import get_logger
from datetime import datetime

logger = get_logger(__name__)


class ProjectStore:
    """Manages project state persistence."""

    def __init__(self, projects_dir: Optional[Path] = None):
        self.projects_dir = projects_dir or settings.projects_dir

    def _get_project_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id

    def _get_state_file(self, project_id: str) -> Path:
        return self._get_project_dir(project_id) / "state.json"

    def create_project(self, project_id: str, input_video: str, context: Optional[str] = None) -> ProjectState:
        """Create a new project."""
        project_dir = self._get_project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (project_dir / "frames").mkdir(exist_ok=True)
        (project_dir / "audio").mkdir(exist_ok=True)

        state = ProjectState(
            project_id=project_id,
            input_video=input_video,
            context=context,
            current_step=PipelineStep.PENDING
        )

        self.save_state(state)
        logger.info(f"Created project: {project_id}")
        return state

    def save_state(self, state: ProjectState) -> None:
        """Save project state to disk."""
        state_file = self._get_state_file(state.project_id)

        # Update timestamp
        state_dict = state.model_dump(mode="json")
        state_dict["updated_at"] = datetime.now().isoformat()

        with open(state_file, "w") as f:
            json.dump(state_dict, f, indent=2, default=str)

    def load_state(self, project_id: str) -> Optional[ProjectState]:
        """Load project state from disk."""
        state_file = self._get_state_file(project_id)

        if not state_file.exists():
            return None

        with open(state_file, "r") as f:
            data = json.load(f)

        return ProjectState(**data)

    def update_step(self, project_id: str, step: PipelineStep, error: Optional[str] = None) -> ProjectState:
        """Update the current pipeline step."""
        state = self.load_state(project_id)
        if not state:
            raise ValueError(f"Project not found: {project_id}")

        new_state = state.model_copy(update={
            "current_step": step,
            "error": error
        })

        self.save_state(new_state)
        return new_state

    def get_project_dir(self, project_id: str) -> Path:
        """Get the project directory path."""
        return self._get_project_dir(project_id)

    def list_projects(self) -> list[str]:
        """List all project IDs."""
        if not self.projects_dir.exists():
            return []
        return [d.name for d in self.projects_dir.iterdir() if d.is_dir()]


# Singleton instance
project_store = ProjectStore()
