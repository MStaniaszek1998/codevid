"""Prompt templates for LLM interactions."""

SCRIPT_GENERATION_PROMPT = """\
Create a concise video tutorial script from an automated test.

## Test Information
Name: {test_name}
Application: {app_name}
Purpose: {test_purpose}

## Test Steps
{formatted_steps}

## Output Format
Generate JSON with this structure:
{{
  "title": "Short tutorial title (3-6 words)",
  "introduction": "One sentence stating what viewers will accomplish.",
  "segments": [
    {{"step_index": 0, "text": "Direct narration for step...", "timing_hint": 2.5}},
    {{"step_index": 1, "text": "Direct narration for step...", "timing_hint": 2.0}}
  ],
  "conclusion": "One sentence confirming the result."
}}

## Narration Rules

REQUIRED STYLE:
- Use imperative mood: "Click the Submit button" not "Now we click Submit"
- Be action-specific: use exact values from steps (e.g., "Enter admin@acme.com" not "Enter your email")
- One sentence per step unless combining related actions
- Address viewer as "you" only when necessary

PATTERNS TO AVOID (never use these):
- Weak openings: "So," "Now," "Okay," "Alright," "Next," "First,"
- Filler phrases: "go ahead and," "we're going to," "let's," "we'll"
- Redundant commentary: "As you can see," "Notice how," "You'll notice"
- Meta-narration: "In this step," "What we're doing here is," "The next thing is"
- Wait/load narration: Never mention waiting, loading, or forms appearing

SKIP ENTIRELY:
- Do not create segments for wait_for_timeout, wait_for_selector, or similar wait actions
- Do not narrate page loads or element appearance

## Timing
- timing_hint: seconds for TTS audio (typically 1.5-3.0 seconds per sentence)
- Match timing to action complexity, not narration length
"""

STEP_ENHANCEMENT_PROMPT = """\
Convert this test action into brief tutorial narration.

Action: {action}
Target: {target}
Value: {value}
Context: {context}

RULES:
- Write ONE sentence maximum
- Use imperative mood: "Click Submit" not "Now we click Submit"
- Include exact values: "Enter 138 in the price field" not "Enter a value"
- Skip wait/load actions entirely (return empty string)

NEVER USE:
- "So," "Now," "Okay," "Next," "First," "Let's," "We'll"
- "go ahead and," "we're going to," "you'll want to"
- "As you can see," "Notice how," "Wait for"

Return ONLY the narration text, nothing else.
"""

INTRO_GENERATION_PROMPT = """\
Create a brief introduction for a video tutorial.

Tutorial topic: {topic}
Application: {app_name}
Steps covered: {step_summary}

Write 2 sentences that:
1. Welcome the viewer
2. Explain what they'll learn
3. Set expectations for the tutorial duration

Keep it conversational and engaging.
"""

CONCLUSION_GENERATION_PROMPT = """\
Create a brief conclusion for a video tutorial.

Tutorial topic: {topic}
Application: {app_name}
What was demonstrated: {demo_summary}

Write 2-3 sentences that:
1. Summarize what was shown
2. Remind viewers of key takeaways
3. Optionally suggest next steps

Keep it positive and encouraging.
"""


def format_steps_for_prompt(steps: list) -> str:
    """Format test steps for inclusion in prompts."""
    lines = []
    for i, step in enumerate(steps, 1):
        value_str = f" with value '{step.value}'" if step.value else ""
        lines.append(f"{i}. {step.action.value.upper()}: {step.target}{value_str}")
    return "\n".join(lines)
