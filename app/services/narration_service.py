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

    # Update segments with narration, ensuring minimum word count
    updated_segments = []
    for i, segment in enumerate(state.segments):
        narration = narrations[i] if i < len(narrations) else segment.description

        duration = segment.end_time - segment.start_time
        words = _count_words(narration)
        min_words = _get_min_words(duration)
        max_words = _get_max_words(duration)

        # Check if narration is too short
        if words < min_words:
            logger.warning(f"Segment {i}: Only {words} words, minimum is {min_words}. Extending narration.")
            # Extend with description context
            if segment.description and len(segment.description) > len(narration):
                narration = f"{narration} {segment.description}"
            else:
                # Add generic filler based on context
                narration = f"{narration} Let's take a closer look at what's happening here and understand the key details of this step."
            words = _count_words(narration)
            logger.info(f"Segment {i}: Extended to {words} words")

        if words > max_words:
            logger.info(f"Segment {i}: {words} words (max {max_words}) - OK, video will freeze")

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
        # Target words for this duration
        target_words = int((duration / 60) * wpm)
        # Minimum: at least 60% of target, or 15 words minimum (ensures substantial content)
        min_words = max(15, int(target_words * 0.6))
        # Maximum: 120% of target (we have freeze frames so slightly longer is OK)
        max_words = max(20, int(target_words * 1.2))

        segments_text += f"""
SEGMENT {seg['segment_id'] + 1}:
- Time: {seg['start_time']:.1f}s - {seg['end_time']:.1f}s ({duration:.1f} seconds)
- WORD COUNT: {min_words}-{max_words} words (aim for {target_words} words)
- What happens: {seg['description'][:500]}
"""

    prompt = f"""Write ENGAGING voiceover narration for a product demo video. Create SUBSTANTIAL narration for each segment - never just a few words.

{"PRODUCT CONTEXT: " + context if context else ""}

SEGMENTS TO NARRATE:
{segments_text}

CRITICAL REQUIREMENTS:

1. SUBSTANTIAL NARRATION - Each segment MUST have meaningful content:
   - NEVER write just 1-5 words for a segment
   - Each segment should have AT LEAST the minimum word count shown
   - Describe what's happening, explain why it matters, guide the viewer
   - If the visual is simple, add context, tips, or explain the significance

2. CONTINUOUS NARRATIVE FLOW:
   - Write as ONE continuous script divided into segments
   - Each segment should connect to the next naturally
   - Use bridges: "Now...", "Next...", "From here...", "Notice how...", "This allows us to..."

3. ENGAGING STYLE:
   - Conversational tone: "Let's", "we'll", "you can see", "notice how"
   - Explain the WHY, not just the WHAT
   - Add value: tips, context, benefits
   - Sound like a friendly expert giving a personal demo

4. FILL THE TIME:
   - The video will PAUSE if your narration is longer than the segment
   - So it's BETTER to have slightly more narration than too little
   - Empty silence during video playback is BAD - always have something to say

EXAMPLE OF GOOD SUBSTANTIAL NARRATION:
SEGMENT 1: (for a 5-second clip showing a dashboard)
"Here's our main dashboard where you can see all your key metrics at a glance. Notice the real-time updates happening in the sidebar - that's your live transaction feed."

EXAMPLE OF BAD MINIMAL NARRATION:
SEGMENT 1:
"The dashboard." (TOO SHORT! This leaves 4 seconds of silence!)

OUTPUT FORMAT - Write SUBSTANTIAL narration for each:

SEGMENT 1:
[{min_words}-{max_words} words of engaging narration]

SEGMENT 2:
[continues the story with substantial content]

...continue for all {len(segments_info)} segments."""

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
        Max words (with 20% buffer since we have freeze frames)
    """
    max_words = int((duration / 60) * wpm * 1.2)
    return max(20, max_words)


def _get_min_words(duration: float, wpm: int = 130) -> int:
    """Calculate minimum words for a segment duration.

    Args:
        duration: Segment duration in seconds
        wpm: Words per minute (130 is comfortable pace)

    Returns:
        Minimum words (at least 60% of target, minimum 15 words)
    """
    target_words = int((duration / 60) * wpm)
    min_words = int(target_words * 0.6)
    return max(15, min_words)  # Minimum 15 words to ensure substantial content


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
