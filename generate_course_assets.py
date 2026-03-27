#!/usr/bin/env python3
"""
Scotty Course Asset Generator
Generates learning-style adapted content for all 10 course days using Claude.

Usage:
    python generate_course_assets.py              # All 40 files
    python generate_course_assets.py 1            # All 4 styles for Day 1
    python generate_course_assets.py 1 visual     # Just Day 1 Visual
"""

import os
import sys
import anthropic
from pathlib import Path

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

BASE_PATH = "./course_materials"
ADAPTED_PATH = f"{BASE_PATH}/adapted"

LEARNING_STYLES = ["visual", "auditory", "reading_writing", "kinesthetic"]

STYLE_INSTRUCTIONS = {
    "visual": """You are adapting for VISUAL learners. Your style guidelines:
- Lead with rich metaphors, analogies, and described mental images
- Use "picture this...", "imagine...", "visualise..." frequently
- Create infographic-style text with clear visual hierarchy
- Describe abstract concepts as scenes, landscapes, or objects
- Journal prompts should invite them to sketch, map, or visualise
- Exercises should include visualisation components
- Tone: warm, vivid, imaginative — like a documentary narrator who actually cares""",

    "auditory": """You are adapting for AUDITORY learners. Your style guidelines:
- Write like Scotty is talking out loud — conversational rhythm, natural speech patterns
- Use repetition, call-and-response, "say this out loud..." moments
- Include suggested ambient sounds/music mood for the session
- Short sentences with spoken-word flow. Read it aloud in your head as you write.
- Journal prompts should invite voice memos, talking to themselves, or dialogue
- Exercises should have spoken affirmations or out-loud components
- Tone: like a trusted podcast host — intimate, direct, rhythmic""",

    "reading_writing": """You are adapting for READING/WRITING learners. Your style guidelines:
- Rich, structured text with clear headers and sub-sections
- Dense but flowing prose that rewards careful reading
- Extended, layered journal prompts with reflection frameworks
- Use numbered steps, bullet points, and structured frameworks
- Include "for your notes..." sections with key concepts to write down
- Exercises should involve writing, lists, or structured reflection
- Tone: thoughtful, literary, warm academic — like a therapist who also writes essays""",

    "kinesthetic": """You are adapting for KINESTHETIC learners. Your style guidelines:
- Lead with the EXERCISE before the theory — do first, understand second
- Body-based language throughout: "notice what happens in your body", "feel this"
- Ground everything in physical sensation and real-world action
- Short explanations. Long, detailed action steps.
- Journal prompts should connect to physical memory or body experience
- Exercises are front and centre — movement, breathing, physical grounding
- Tone: energetic, direct, action-first — like a brilliant personal trainer who gets the emotional side""",
}

SYSTEM_BASE = """You are Scotty, an AI coach for the Social Anxiety Reset — a 10-session program helping Gen Z overcome social anxiety using CBT principles.

You are adapting existing course content for a specific learning style. Keep ALL core CBT concepts and therapeutic content intact. Adapt the FORMAT, STRUCTURE, and TONE to match the learning style described below.

Scotty's voice stays present throughout — warm, real, slightly witty, Gen Z-native, never forced or clinical.

Output the full adapted content in this EXACT markdown format (keep all section headers exactly as shown):

# Day [N]: [Title]

## Lesson Content
[adapted lesson content]

## Journal Prompts
[adapted journal prompts as a bulleted list]

## Daily Exercise
[adapted exercise — lead with action for kinesthetic, visualisation for visual, etc.]

## Motivation
[adapted closing motivation]

## AI Support Guidance
[adapted Scotty in-conversation guidance for this learning style — what Scotty says and how]"""


def read_base_content(day: int) -> str:
    file_path = f"{BASE_PATH}/day{day}-content.md.txt"
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def generate_adapted_content(base_content: str, day: int, style: str) -> str:
    system = SYSTEM_BASE + "\n\n" + STYLE_INSTRUCTIONS[style]
    prompt = f"""Adapt this Day {day} course content for a {style} learner.
Remember: same CBT content, adapted presentation and tone.

BASE CONTENT:
{base_content}"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2500,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def save_adapted_content(content: str, day: int, style: str) -> str:
    style_dir = Path(f"{ADAPTED_PATH}/{style}")
    style_dir.mkdir(parents=True, exist_ok=True)
    file_path = style_dir / f"day{day}-{style}.md.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(file_path)


def generate_for(day: int, style: str, force: bool = False):
    output_path = Path(f"{ADAPTED_PATH}/{style}/day{day}-{style}.md.txt")
    if output_path.exists() and not force:
        print(f"  ⏭️  Already exists — Day {day} {style}")
        return

    print(f"  ✨ Generating Day {day} — {style}...", end=" ", flush=True)
    try:
        base = read_base_content(day)
        adapted = generate_adapted_content(base, day, style)
        path = save_adapted_content(adapted, day, style)
        print(f"✅  ({path})")
    except Exception as e:
        print(f"❌  Error: {e}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    days = range(1, 11)
    styles = LEARNING_STYLES

    if len(args) >= 1:
        days = [int(args[0])]
    if len(args) >= 2:
        styles = [args[1]]

    print("🎓  Scotty Course Asset Generator")
    print(f"    Days:   {list(days)}")
    print(f"    Styles: {styles}")
    print(f"    Force:  {force}")
    print()

    for day in days:
        print(f"📚  Day {day}:")
        for style in styles:
            generate_for(day, style, force=force)

    print("\n✨  Done! Adapted files saved to course_materials/adapted/")
