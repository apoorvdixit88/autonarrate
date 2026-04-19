import asyncio
import re
from pathlib import Path
from typing import Optional
import edge_tts

from app.models import ProjectState, PipelineStep
from app.config import settings
from app.services.project_store import project_store
from app.utils.logger import get_logger

logger = get_logger(__name__)


def clean_text_for_tts(text: str) -> str:
    """Remove markdown and special characters that TTS reads literally."""
    if not text:
        return text

    # Remove markdown bold/italic: **text**, *text*, __text__, _text_
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'\*(.+?)\*', r'\1', text)       # *italic*
    text = re.sub(r'__(.+?)__', r'\1', text)       # __underline__
    text = re.sub(r'_(.+?)_', r'\1', text)         # _italic_

    # Remove markdown headers: # Header
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)

    # Remove markdown links: [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Remove markdown code: `code` and ```code```
    text = re.sub(r'```[^`]*```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remove bullet points: - item, * item
    text = re.sub(r'^[\-\*]\s+', '', text, flags=re.MULTILINE)

    # Remove numbered lists: 1. item
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)

    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text


async def synthesize_speech(
    text: str,
    output_path: Path,
    voice: str = "en-US-ChristopherNeural"
) -> bool:
    """Synthesize speech using Edge TTS."""
    try:
        # Clean text to remove markdown formatting
        clean_text = clean_text_for_tts(text)
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(str(output_path))
        return output_path.exists()
    except Exception as e:
        logger.error(f"TTS failed: {e}")
        return False


async def synthesize_all_segments(state: ProjectState, max_concurrent: int = 5) -> ProjectState:
    """Synthesize narration audio for all segments in parallel."""
    logger.info(f"Synthesizing narration audio for {len(state.segments)} segments (parallel, max {max_concurrent} concurrent)")

    state = state.model_copy(update={"current_step": PipelineStep.SYNTHESIZING_AUDIO})
    project_store.save_state(state)

    project_dir = project_store.get_project_dir(state.project_id)
    audio_dir = project_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    # Semaphore to limit concurrent TTS calls
    semaphore = asyncio.Semaphore(max_concurrent)

    async def synthesize_one(segment):
        async with semaphore:
            audio_path = audio_dir / f"segment_{segment.segment_id:03d}.mp3"

            if segment.narration and segment.narration.strip():
                logger.info(f"Synthesizing segment {segment.segment_id + 1}/{len(state.segments)}")
                success = await synthesize_speech(
                    text=segment.narration,
                    output_path=audio_path,
                    voice=state.voice
                )

                if success:
                    return segment.model_copy(update={"audio_path": str(audio_path)})
                else:
                    logger.warning(f"TTS failed for segment {segment.segment_id}")
                    return segment
            else:
                logger.warning(f"No narration for segment {segment.segment_id}")
                return segment

    # Run all TTS in parallel (with concurrency limit)
    updated_segments = await asyncio.gather(*[synthesize_one(seg) for seg in state.segments])

    # Sort by segment_id to maintain order
    updated_segments = sorted(updated_segments, key=lambda s: s.segment_id)

    state = state.model_copy(update={"segments": updated_segments})
    project_store.save_state(state)

    logger.info("Audio synthesis complete")
    return state


async def list_available_voices() -> list[dict]:
    """List available Edge TTS voices."""
    voices = await edge_tts.list_voices()
    return [
        {"name": v["Name"], "gender": v["Gender"], "locale": v["Locale"]}
        for v in voices
        if v["Locale"].startswith("en-")
    ]
