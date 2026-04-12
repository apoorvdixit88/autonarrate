from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class PipelineStep(str, Enum):
    PENDING = "pending"
    INGESTING = "ingesting"
    SEGMENTING = "segmenting"
    EXTRACTING_FRAMES = "extracting_frames"
    ANALYZING_FRAMES = "analyzing_frames"
    GENERATING_SCRIPT = "generating_script"
    SYNTHESIZING_AUDIO = "synthesizing_audio"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoMetadata(BaseModel):
    """Metadata extracted from input video."""
    model_config = {"frozen": True}

    duration: float
    width: int
    height: int
    fps: float
    codec: str
    file_size: int


class FrameData(BaseModel):
    """Data for a single extracted frame."""
    model_config = {"frozen": True}

    frame_path: str
    timestamp: float
    ocr_text: Optional[str] = None


class SegmentAnalysis(BaseModel):
    """Analysis result for a video segment."""
    model_config = {"frozen": True}

    segment_id: int
    start_time: float
    end_time: float
    frames: list[FrameData]
    description: str = ""
    narration: str = ""
    audio_path: Optional[str] = None
    speed_adjustment: Optional[float] = None  # <1.0 means slow down video (e.g., 0.75 = 25% slower)


class ProjectState(BaseModel):
    """Complete project state - saved after each pipeline step."""
    model_config = {"frozen": True}

    project_id: str
    input_video: str
    context: Optional[str] = None
    voice: str = "en-GB-LibbyNeural"
    current_step: PipelineStep = PipelineStep.PENDING
    error: Optional[str] = None
    metadata: Optional[VideoMetadata] = None
    segments: list[SegmentAnalysis] = Field(default_factory=list)
    output_video: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ProjectResponse(BaseModel):
    """API response for project status."""
    project_id: str
    current_step: PipelineStep
    error: Optional[str] = None
    segment_count: int = 0
    output_ready: bool = False


class UploadRequest(BaseModel):
    """Request model for video upload."""
    context: Optional[str] = None
