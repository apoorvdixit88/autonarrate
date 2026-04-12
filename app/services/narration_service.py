import subprocess
import asyncio
from typing import Optional

from app.models import ProjectState, SegmentAnalysis, PipelineStep
from app.config import settings
from app.services.project_store import project_store
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def generate_narration_script(state: ProjectState) -> ProjectState:
    """
    Generate narration script for all segments.
    Uses Claude Code to create coherent narration from segment descriptions.
    AI is instructed to keep narration within word limits so video length stays unchanged.
    """
    logger.info("Generating narration script")

    state = state.model_copy(update={"current_step": PipelineStep.GENERATING_SCRIPT})
    project_store.save_state(state)

    # Build context for narration generation
    segments_info = []
    for seg in state.segments:
        segments_info.append({
            "segment_id": seg.segment_id,
            "start_time": seg.start_time,
            "end_time": seg.end_time,
            "duration": seg.end_time - seg.start_time,
            "description": seg.description
        })

    prompt = _build_narration_prompt(segments_info, state.context, state.metadata.duration if state.metadata else 0)

    try:
        narration_result = await asyncio.to_thread(_run_claude_code_narration, prompt)
        narrations = _parse_narration_result(narration_result, len(state.segments))
    except Exception as e:
        logger.error(f"Narration generation failed: {e}")
        # Fallback: use descriptions as narration
        narrations = [seg.description for seg in state.segments]

    # Update segments with narration (no speed adjustments for AI-generated content)
    updated_segments = []
    for i, segment in enumerate(state.segments):
        narration = narrations[i] if i < len(narrations) else segment.description

        # Log if AI exceeded word limit (for debugging)
        duration = segment.end_time - segment.start_time
        words = _count_words(narration)
        max_words = _get_max_words(duration)
        if words > max_words:
            logger.warning(f"Segment {i}: AI generated {words} words, max was {max_words}")

        updated_segment = segment.model_copy(update={"narration": narration})
        updated_segments.append(updated_segment)

    state = state.model_copy(update={"segments": updated_segments})
    project_store.save_state(state)

    logger.info("Narration script generation complete")
    return state


def _build_narration_prompt(
    segments_info: list[dict],
    context: Optional[str],
    total_duration: float
) -> str:
    """Build prompt for narration generation."""

    # Calculate word limits based on duration (130 WPM = comfortable pace)
    wpm = 130

    segments_text = ""
    for seg in segments_info:
        duration = seg['duration']
        max_words = int((duration / 60) * wpm)
        # Minimum 8 words, leave 20% buffer for pauses
        max_words = max(8, int(max_words * 0.8))

        segments_text += f"""
SEGMENT {seg['segment_id'] + 1}:
- Time: {seg['start_time']:.1f}s - {seg['end_time']:.1f}s ({duration:.1f} seconds)
- MAX WORDS: {max_words} words (STRICT LIMIT)
- What happens: {seg['description'][:500]}
"""

    prompt = f"""Write voiceover narration for a product walkthrough video. This should sound like ONE CONTINUOUS SCRIPT read by a single narrator - smooth and connected, not choppy separate sentences.
{"Context: " + context if context else ""}

{segments_text}

MOST IMPORTANT - NARRATIVE FLOW:
Think of this as writing ONE script that happens to be divided into timed segments. When read aloud back-to-back, it should flow naturally like a conversation - NOT sound like separate disconnected statements.

RULES:
1. WORD COUNT IS STRICT - Each segment has a max word limit. Do NOT exceed it.
2. ONE CONTINUOUS VOICE - Write as if you're giving a live demo to someone sitting next to you.
3. CONNECT EVERY SEGMENT - Each segment should lead into the next. Use bridges like:
   - "Now...", "Next...", "From here...", "And...", "So...", "Here..."
   - "Once that's done...", "With that set up...", "Now that we've..."
   - "You'll notice...", "This brings us to...", "Moving on..."

GOOD FLOW (reads as one continuous narration):
"Let's start by opening the settings. [SEG 1] Now we can customize our preferences here. [SEG 2] Once you've made your selections, just hit save. [SEG 3] And that's it - your changes are applied instantly. [SEG 4]"

BAD (choppy, disconnected):
"The user opens settings." [SEG 1] "Preferences are displayed." [SEG 2] "The save button is clicked." [SEG 3] "Changes are saved." [SEG 4]

STYLE:
- Conversational: "Let's", "we'll", "you can", "notice how"
- Short sentences that flow together
- End segments with natural pause points, but lead into what's next
- Skip obvious details - focus on what matters

OUTPUT FORMAT:
SEGMENT 1:
[narration that sets up the story]

SEGMENT 2:
[continues naturally from segment 1]

...and so on for all {len(segments_info)} segments."""

    return prompt


def _run_claude_code_narration(prompt: str) -> str:
    """Run Claude Code for narration generation."""
    cmd = [
        settings.claude_code_path,
        "-p", prompt,
        "--dangerously-skip-permissions"
    ]

    logger.info("Running Claude Code for narration generation")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=180
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude Code failed: {result.stderr}")

    return result.stdout.strip()


def _parse_narration_result(result: str, num_segments: int) -> list[str]:
    """Parse the narration result into individual segment narrations."""
    narrations = []

    # Try to parse structured output
    import re

    # Pattern to match "SEGMENT N:" followed by content
    pattern = r'SEGMENT\s+(\d+):\s*(.*?)(?=SEGMENT\s+\d+:|$)'
    matches = re.findall(pattern, result, re.DOTALL | re.IGNORECASE)

    if matches:
        # Sort by segment number and extract narrations
        sorted_matches = sorted(matches, key=lambda x: int(x[0]))
        narrations = [m[1].strip() for m in sorted_matches]
    else:
        # Fallback: split by double newlines or numbered items
        parts = re.split(r'\n\n+|\d+\.\s+', result)
        narrations = [p.strip() for p in parts if p.strip()]

    # Ensure we have enough narrations
    while len(narrations) < num_segments:
        narrations.append("[Narration not generated]")

    return narrations[:num_segments]


def _count_words(text: str) -> int:
    """Count words in text."""
    if not text:
        return 0
    # Simple word count: split by whitespace
    words = text.strip().split()
    return len(words)


def _get_max_words(duration: float, wpm: int = 130) -> int:
    """Calculate max words for a segment duration.

    Args:
        duration: Segment duration in seconds
        wpm: Words per minute (130 is comfortable pace)

    Returns:
        Max words (with 15% buffer for natural pauses)
    """
    max_words = int((duration / 60) * wpm * 0.85)
    return max(8, max_words)  # Minimum 8 words


def _calculate_speed_adjustment(narration: str, duration: float) -> Optional[float]:
    """Calculate speed adjustment needed if narration exceeds word limit.

    Returns:
        - None if no adjustment needed (narration fits within limit)
        - Float < 1.0 representing slowdown factor (e.g., 0.75 = 25% slower)
    """
    words = _count_words(narration)
    max_words = _get_max_words(duration)

    if words <= max_words:
        return None  # No adjustment needed

    # Calculate how much slower we need to play
    # If we have 20 words but max is 15, we need to slow down by 20/15 = 1.33x
    # Speed factor = max_words / words = 15/20 = 0.75 (25% slower)
    speed_factor = max_words / words

    # Cap slowdown at 50% (speed factor 0.5) - beyond that sounds unnatural
    speed_factor = max(0.5, speed_factor)

    # Round to nearest 5% for cleaner values
    speed_factor = round(speed_factor * 20) / 20  # e.g., 0.75, 0.80, 0.85

    logger.debug(f"Words: {words}, Max: {max_words}, Speed adjustment: {speed_factor}")
    return speed_factor
