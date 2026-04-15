import subprocess
import asyncio
from pathlib import Path
from typing import Optional
import json
import re

from app.models import ProjectState, SegmentAnalysis, FrameData, PipelineStep
from app.config import settings
from app.services.project_store import project_store
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ClaudeCodeVision:
    """Vision analysis using Claude Code subprocess."""

    def __init__(self, claude_path: str = "claude"):
        self.claude_path = claude_path

    async def analyze_frame(self, frame_path: Path, context: Optional[str] = None) -> str:
        """Analyze a single frame using Claude Code."""
        prompt = self._build_frame_prompt(frame_path, context)

        try:
            result = await asyncio.to_thread(
                self._run_claude_code,
                prompt,
                str(frame_path)
            )
            return result
        except Exception as e:
            logger.error(f"Claude Code analysis failed: {e}")
            return f"[Analysis failed: {e}]"

    async def analyze_segment(
        self,
        frames: list[FrameData],
        segment_id: int,
        start_time: float,
        end_time: float,
        context: Optional[str] = None
    ) -> str:
        """Analyze multiple frames from a segment."""
        if not frames:
            return "[No frames to analyze]"

        # Build prompt with all frame paths
        frame_paths = [f.frame_path for f in frames]
        prompt = self._build_segment_prompt(frame_paths, segment_id, start_time, end_time, context)

        try:
            # Use the first frame for the image input, include others in prompt
            result = await asyncio.to_thread(
                self._run_claude_code_multi,
                prompt,
                frame_paths
            )
            return result
        except Exception as e:
            logger.error(f"Segment analysis failed: {e}")
            return f"[Analysis failed: {e}]"

    def _build_frame_prompt(self, frame_path: Path, context: Optional[str] = None) -> str:
        """Build prompt for single frame analysis."""
        base_prompt = """Analyze this frame from a video. Describe what you see concisely:
- What UI elements, text, or content is visible?
- What action or state is being shown?
- Any notable visual elements?

Be specific but brief (2-3 sentences max)."""

        if context:
            base_prompt = f"Context: {context}\n\n{base_prompt}"

        return base_prompt

    def _build_segment_prompt(
        self,
        frame_paths: list[str],
        segment_id: int,
        start_time: float,
        end_time: float,
        context: Optional[str] = None
    ) -> str:
        """Build prompt for segment analysis."""
        duration = end_time - start_time

        prompt = f"""Analyze this video segment (segment {segment_id + 1}, {start_time:.1f}s to {end_time:.1f}s, duration {duration:.1f}s).

I'm showing you {len(frame_paths)} key frames from this segment. Describe what's happening:

1. What is the user doing or what is being demonstrated?
2. What UI elements, screens, or content are visible?
3. What's the progression or flow across these frames?

Be specific and descriptive but concise (3-5 sentences). Focus on what would be useful for narration."""

        if context:
            prompt = f"Video context: {context}\n\n{prompt}"

        return prompt

    def _run_claude_code(self, prompt: str, image_path: str) -> str:
        """Run Claude Code with a prompt and image."""
        # Build the command - use -p for print mode (non-interactive)
        # Claude Code can read images via its Read tool
        full_prompt = f"Read the image file at {image_path} and analyze it. {prompt}"

        cmd = [
            self.claude_path,
            "-p", full_prompt,
            "--dangerously-skip-permissions"
        ]

        logger.info(f"Running Claude Code for image: {Path(image_path).name}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=Path(image_path).parent
        )

        if result.returncode != 0:
            logger.error(f"Claude Code error: {result.stderr}")
            raise RuntimeError(f"Claude Code failed: {result.stderr}")

        # Parse output - remove any tool call artifacts
        output = result.stdout.strip()
        return self._clean_output(output)

    def _run_claude_code_multi(self, prompt: str, image_paths: list[str]) -> str:
        """Run Claude Code with multiple images."""
        # Build prompt that references all images
        images_list = "\n".join([f"- {p}" for p in image_paths])
        full_prompt = f"""Read and analyze these video frame images:
{images_list}

After reading each image file, provide your analysis.

{prompt}"""

        cmd = [
            self.claude_path,
            "-p", full_prompt,
            "--dangerously-skip-permissions"
        ]

        logger.info(f"Running Claude Code for {len(image_paths)} frames")

        # Run from the directory containing the frames
        work_dir = Path(image_paths[0]).parent if image_paths else Path.cwd()

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=work_dir
        )

        if result.returncode != 0:
            logger.error(f"Claude Code error: {result.stderr}")
            raise RuntimeError(f"Claude Code failed: {result.stderr}")

        output = result.stdout.strip()
        return self._clean_output(output)

    def _clean_output(self, output: str) -> str:
        """Clean Claude Code output to extract just the analysis."""
        # Remove common artifacts
        lines = output.split("\n")
        cleaned_lines = []

        skip_patterns = [
            "Tool call:",
            "Reading file:",
            "╭", "╰", "│",
            "```",
        ]

        for line in lines:
            if any(p in line for p in skip_patterns):
                continue
            if line.strip():
                cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()


class OpenCodeVision:
    """Vision analysis using OpenCode subprocess."""

    def __init__(self, opencode_path: str = "opencode"):
        self.opencode_path = opencode_path

    async def analyze_segment(
        self,
        frames: list[FrameData],
        segment_id: int,
        start_time: float,
        end_time: float,
        context: Optional[str] = None
    ) -> str:
        """Analyze segment using OpenCode."""
        if not frames:
            return "[No frames to analyze]"

        frame_paths = [f.frame_path for f in frames]
        prompt = self._build_segment_prompt(frame_paths, segment_id, start_time, end_time, context)

        try:
            result = await asyncio.to_thread(
                self._run_opencode,
                prompt,
                frame_paths
            )
            return result
        except Exception as e:
            logger.error(f"OpenCode analysis failed: {e}")
            return f"[Analysis failed: {e}]"

    def _build_segment_prompt(
        self,
        frame_paths: list[str],
        segment_id: int,
        start_time: float,
        end_time: float,
        context: Optional[str] = None
    ) -> str:
        """Build prompt for segment analysis."""
        duration = end_time - start_time

        prompt = f"""Analyze this video segment (segment {segment_id + 1}, {start_time:.1f}s to {end_time:.1f}s, duration {duration:.1f}s).

I'm showing you {len(frame_paths)} key frames from this segment. Describe what's happening:

1. What is the user doing or what is being demonstrated?
2. What UI elements, screens, or content are visible?
3. What's the progression or flow across these frames?

Be specific and descriptive but concise (3-5 sentences). Focus on what would be useful for narration."""

        if context:
            prompt = f"Video context: {context}\n\n{prompt}"

        return prompt

    def _run_opencode(self, prompt: str, image_paths: list[str]) -> str:
        """Run OpenCode with multiple images."""
        images_list = "\n".join([f"- {p}" for p in image_paths])
        full_prompt = f"""Read and analyze these video frame images:
{images_list}

After reading each image file, provide your analysis.

{prompt}"""

        cmd = [
            self.opencode_path,
            "-p", full_prompt,
            "--dangerously-skip-permissions"
        ]

        logger.info(f"Running OpenCode for {len(image_paths)} frames")

        work_dir = Path(image_paths[0]).parent if image_paths else Path.cwd()

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=work_dir
        )

        if result.returncode != 0:
            logger.error(f"OpenCode error: {result.stderr}")
            raise RuntimeError(f"OpenCode failed: {result.stderr}")

        output = result.stdout.strip()
        return self._clean_output(output)

    def _clean_output(self, output: str) -> str:
        """Clean OpenCode output to extract just the analysis."""
        lines = output.split("\n")
        cleaned_lines = []

        skip_patterns = [
            "Tool call:",
            "Reading file:",
            "╭", "╰", "│",
            "```",
        ]

        for line in lines:
            if any(p in line for p in skip_patterns):
                continue
            if line.strip():
                cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()


class OllamaVision:
    """Fallback vision analysis using Ollama."""

    def __init__(self, model: str = "llama3.2-vision", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host

    async def analyze_segment(
        self,
        frames: list[FrameData],
        segment_id: int,
        start_time: float,
        end_time: float,
        context: Optional[str] = None
    ) -> str:
        """Analyze segment using Ollama."""
        import base64

        if not frames:
            return "[No frames to analyze]"

        # Use first frame for analysis
        frame_path = Path(frames[0].frame_path)

        with open(frame_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()

        prompt = f"""Analyze this video frame (segment {segment_id + 1}, {start_time:.1f}s to {end_time:.1f}s).
Describe what you see - UI elements, actions, content. Be concise (3-5 sentences).
{"Context: " + context if context else ""}"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_data],
            "stream": False
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(f"{self.host}/api/generate", json=payload)
                response.raise_for_status()
                result = response.json()
                return result.get("response", "[No response]")
        except Exception as e:
            logger.error(f"Ollama analysis failed: {e}")
            return f"[Analysis failed: {e}]"


class OpenAIVision:
    """Vision analysis using OpenAI API directly."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model

    async def analyze_segment(
        self,
        frames: list[FrameData],
        segment_id: int,
        start_time: float,
        end_time: float,
        context: Optional[str] = None
    ) -> str:
        """Analyze segment using OpenAI Vision API."""
        import base64
        import httpx

        if not frames:
            return "[No frames to analyze]"

        duration = end_time - start_time
        prompt = f"""Analyze this video segment (segment {segment_id + 1}, {start_time:.1f}s to {end_time:.1f}s, duration {duration:.1f}s).

Describe what's happening:
1. What is the user doing or what is being demonstrated?
2. What UI elements, screens, or content are visible?
3. What's the progression or flow?

Be specific and descriptive but concise (3-5 sentences). Focus on what would be useful for narration.
{"Video context: " + context if context else ""}"""

        # Encode images
        content = [{"type": "text", "text": prompt}]
        for frame in frames[:4]:  # Limit to 4 frames
            with open(frame.frame_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_data}"}
            })

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": content}],
                        "max_tokens": 500
                    }
                )
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"OpenAI analysis failed: {e}")
            return f"[Analysis failed: {e}]"


class AnthropicVision:
    """Vision analysis using Anthropic API directly."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model

    async def analyze_segment(
        self,
        frames: list[FrameData],
        segment_id: int,
        start_time: float,
        end_time: float,
        context: Optional[str] = None
    ) -> str:
        """Analyze segment using Anthropic Vision API."""
        import base64
        import httpx

        if not frames:
            return "[No frames to analyze]"

        duration = end_time - start_time
        prompt = f"""Analyze this video segment (segment {segment_id + 1}, {start_time:.1f}s to {end_time:.1f}s, duration {duration:.1f}s).

Describe what's happening:
1. What is the user doing or what is being demonstrated?
2. What UI elements, screens, or content are visible?
3. What's the progression or flow?

Be specific and descriptive but concise (3-5 sentences). Focus on what would be useful for narration.
{"Video context: " + context if context else ""}"""

        # Build content with images
        content = []
        for frame in frames[:4]:  # Limit to 4 frames
            with open(frame.frame_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode()
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_data
                }
            })
        content.append({"type": "text", "text": prompt})

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 500,
                        "messages": [{"role": "user", "content": content}]
                    }
                )
                response.raise_for_status()
                result = response.json()
                return result["content"][0]["text"]
        except Exception as e:
            logger.error(f"Anthropic analysis failed: {e}")
            return f"[Analysis failed: {e}]"


def get_vision_service():
    """Get the configured vision service."""
    if settings.vision_backend == "ollama":
        return OllamaVision(
            model=settings.ollama_model,
            host=settings.ollama_host
        )
    elif settings.vision_backend == "opencode":
        return OpenCodeVision(
            opencode_path=settings.opencode_path
        )
    elif settings.vision_backend == "openai":
        return OpenAIVision(
            api_key=settings.openai_api_key,
            model=settings.openai_model
        )
    elif settings.vision_backend == "anthropic":
        return AnthropicVision(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model
        )
    else:
        return ClaudeCodeVision(
            claude_path=settings.claude_code_path
        )


async def analyze_segments(state: ProjectState, max_concurrent: int = 3) -> ProjectState:
    """Analyze all segments using vision service with parallel processing."""
    vision = get_vision_service()

    logger.info(f"Analyzing {len(state.segments)} segments using {settings.vision_backend} (parallel, max {max_concurrent} concurrent)")

    # Update state
    state = state.model_copy(update={"current_step": PipelineStep.ANALYZING_FRAMES})
    project_store.save_state(state)

    # Create semaphore to limit concurrent API calls
    semaphore = asyncio.Semaphore(max_concurrent)

    async def analyze_one(segment, max_retries: int = 2):
        async with semaphore:
            logger.info(f"Analyzing segment {segment.segment_id + 1}/{len(state.segments)}")

            for attempt in range(max_retries):
                description = await vision.analyze_segment(
                    frames=segment.frames,
                    segment_id=segment.segment_id,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    context=state.context
                )

                # Check if analysis succeeded
                if not description.startswith("[Analysis failed"):
                    return segment.model_copy(update={"description": description})

                # Retry if failed
                if attempt < max_retries - 1:
                    logger.warning(f"Segment {segment.segment_id + 1} failed, retrying ({attempt + 2}/{max_retries})...")
                    await asyncio.sleep(2)  # Brief pause before retry

            # All retries exhausted
            logger.error(f"Segment {segment.segment_id + 1} failed after {max_retries} attempts")
            return segment.model_copy(update={"description": description})

    # Run all analyses in parallel (with concurrency limit)
    updated_segments = await asyncio.gather(*[analyze_one(seg) for seg in state.segments])

    # Sort by segment_id to maintain order
    updated_segments = sorted(updated_segments, key=lambda s: s.segment_id)

    # Check for failed analyses - don't continue if vision failed
    failed_segments = [s for s in updated_segments if s.description.startswith("[Analysis failed")]
    if failed_segments:
        failed_ids = [s.segment_id + 1 for s in failed_segments]
        first_error = failed_segments[0].description
        error_msg = f"Vision analysis failed using '{settings.vision_backend}' backend. " \
                    f"Failed segments: {failed_ids}. Error: {first_error}"
        logger.error(error_msg)
        logger.error(f"Please check your {settings.vision_backend} configuration in .env")
        raise RuntimeError(error_msg)

    state = state.model_copy(update={"segments": updated_segments})
    project_store.save_state(state)

    logger.info("Segment analysis complete")
    return state
