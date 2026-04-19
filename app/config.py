from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 3005
    debug: bool = True

    # Vision backend
    vision_backend: str = "claude_code"  # "claude_code", "opencode", "ollama", "openai", or "anthropic"

    # Ollama settings
    ollama_model: str = "llama3.2-vision"
    ollama_host: str = "http://localhost:11434"

    # OpenAI settings (if using openai backend)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Anthropic settings (if using anthropic backend)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # TTS
    tts_voice: str = "en-US-ChristopherNeural"

    # Paths
    projects_dir: Path = Path("./projects")
    claude_code_path: str = "claude"
    opencode_path: str = "opencode"

    # Pipeline settings
    scene_threshold: float = 27.0
    min_segment_duration: float = 3.0  # Merge segments shorter than 3s (fewer segments)
    frames_per_segment: int = 2  # Reduced from 5 for faster processing
    narration_wpm: int = 130
    max_segments: int = 15  # Limit max segments to prevent very long processing

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure projects directory exists
settings.projects_dir.mkdir(parents=True, exist_ok=True)
