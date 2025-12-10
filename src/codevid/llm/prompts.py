"""Prompt templates for LLM interactions."""

SCRIPT_GENERATION_PROMPT = """\
You are creating a video tutorial script based on an automated test.
The tutorial should be educational, clear, and engaging.

## Test Information
Name: {test_name}
Application: {app_name}
Purpose: {test_purpose}

## Test Steps
{formatted_steps}

## Instructions
Generate a video script with:
1. A brief introduction that states the purpose and title of the tutorial.
2. A short “How to do it” segment that previews the plan before individual steps.
3. Narration for each step (explain WHAT is happening and WHY).
4. A conclusion that describes the expected outcome/result after the steps.

For each step narration:
- Use natural, conversational language
- Explain the user intent, not just the action
- Include timing hints for pacing (how long this step takes to show)
- Highlight important UI elements

Output as JSON with this exact structure:
{{
  "title": "Tutorial title here",
  "introduction": "Welcome message, purpose, and what viewers will learn...",
  "segments": [
    {{"step_index": -1, "text": "How to do it: quick overview of the plan...", "timing_hint": 3.0}},
    {{"step_index": 0, "text": "Narration for first step...", "timing_hint": 3.5}},
    {{"step_index": 1, "text": "Narration for second step...", "timing_hint": 2.0}}
  ],
  "conclusion": "Outcome-focused summary of what was demonstrated..."
}}

Important:
- timing_hint is in seconds and should account for the action duration
- Each segment's text should be 1-3 sentences
- Use second person ("you") to address the viewer
- Be specific about UI elements being interacted with
- Make sure that it sounds like a human wrote it, not a machine. This tutorial will be on youtube and needs to sound natural.
"""

STEP_ENHANCEMENT_PROMPT = """\
Convert this test action into natural tutorial narration.

Action: {action}
Target: {target}
Value: {value}
Context: {context}

Write 1-2 sentences explaining this step as if teaching someone.
Focus on the user's goal, not the technical implementation.
Do not use technical jargon like "selector" or "element".
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
