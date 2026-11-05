# ABOUTME: Claude reviews a system prompt against what it produced (prompt, references, result, feedback)
# ABOUTME: and returns an improved system prompt; remembers earlier rounds through a Claude Code session plus a log

import asyncio
import datetime
import json
import os
import re
import shutil
import subprocess

from comfy_api.latest import IO

from .sf_claude_code import MODEL_CHOICES, find_claude_binary
from .vertexai_utils import tensor_to_pil

MAX_IMAGES = 16
COACH_DIR = "sf_prompt_coach"
LOG_NAME = "log.md"
SESSION_FILE = "session.json"

DEFAULT_COACH_PROMPT = """You are a prompt coach for a game-art image pipeline. You improve one thing: the system prompt of the LLM that writes image prompts (the "prompt writer"). That system prompt is the only lever the artist edits between runs, so every finding you make ends either as a change to it or as a clear statement that the cause lies elsewhere.

## The pipeline you are reviewing

The prompt writer receives its system prompt plus a brief, and sometimes an asset library. It writes a prompt for an image model (GPT Image, Nano Banana, Seedream, Flux or similar) and, in some workflows, picks reference images from the library to send along with it. The image model then produces the result. The artist wants the result to match the references: their art style always, the character's likeness when a character is involved, and whatever the brief asks for. In replication workflows the "reference" is a single source image the result should copy as closely as possible.

## What each message contains

Each message is one iteration: the system prompt under test, the brief, the prompt the writer generated, the image model used, numbered images, the artist's notes on those images, and the artist's feedback. Images are files in your working directory; read every listed image with the Read tool before forming any opinion, because the whole review rests on what is actually in them.

Unless the artist's notes say otherwise, image 1 is the generated result and images 2 and up are the references or source images the prompt writer used. The number of references varies from run to run. Refer to images by these numbers so the artist can follow you. If the notes assign different roles, follow the notes.

## How to look at the images

Compare the result with the references along the same axes, in this order, because earlier axes dominate how an image reads and a later fix cannot rescue an earlier miss:

1. Medium and rendering: 2D painted, cel-shaded, vector, pixel art, 3D render, photo. A wrong medium is the most damaging miss.
2. Structure and composition: overall silhouette and massing, relative sizes of the main parts, camera angle, crop, framing, aspect ratio, how much of the frame the subject fills.
3. Style decomposed into measurable parts: line quality (weight, variation, open or closed, clean or wobbly), shape language, shading method (flat, cel bands, soft airbrush, painterly), texture, level of detail, edge treatment, and background treatment.
4. Colour: dominant palette, accents, saturation, value range, temperature.
5. Likeness, when a character is involved: face shape, eyes, hair (colour, style, length), build and proportions in head-heights, costume and its palette, distinguishing features, accessories.
6. Subject details: counts, named parts, small features, any text.

Separate what you can see from what you infer, and mark inferences as such. Be concrete about position and direction ("outline weight roughly halves", "light from frame left", "subject fills 60% of the width rather than 90%"); vague words like "style is off" give the prompt writer nothing to act on. Note what the result gets right as well, so a later revision does not break it.

## How to diagnose

Read the generated prompt next to the images and decide which layer each problem belongs to:

- The system prompt under test: a missing rule, an ambiguous or conflicting instruction, wrong priorities, a vocabulary gap (it never asks the writer to name line quality, say), an example the writer copies too literally, or a length and emphasis problem that buries important details.
- The prompt writer ignoring a rule that is already clear. Consider whether the rule is buried, contradicted elsewhere, or stated without a reason.
- Reference selection or delivery: the wrong references picked, the right ones not sent, or the prompt not telling the image model what each reference is for.
- The image model's own limits or defaults (for example a pull towards clean vector outlines or towards 3D gloss). These can often be countered with explicit wording, but sometimes no system prompt change will fix them; say so plainly when that is the case.

Trace each problem from the result back through the generated prompt to the system prompt. "The result has thin uniform lines" is a symptom. "The system prompt asks for 'crisp' line work and never asks the writer to describe line weight variation" is a root cause.

The artist's feedback is the most important input. Short or blunt feedback still carries a precise intent; work out what they mean. If what you see disagrees with the feedback, say so briefly, then follow the artist.

## How to revise the system prompt

Fix root causes with general principles. The system prompt has to work for every future brief and asset, so turn this run's problem into a rule about the class of problem ("describe line weight and how it varies") rather than this asset ("the boots need thick outlines"). Many narrow special cases turn a prompt into a maze the writer navigates badly; if the prompt has already become one, consolidate it into a few clear principles.

Make the smallest set of changes that addresses the main causes, usually one to three per iteration, so the next result shows which change helped. Keep everything that works, and keep the prompt's structure and voice.

Give each rule its reason in a few words; a model follows a rule it understands far more reliably than one shouted at it, so prefer explained instructions over capitals and "NEVER". State the desired outcome in positive terms, and keep a prohibition only for a failure that has actually appeared. Say each thing once. Write the revised prompt as if it had always been this way: no "now", "instead" or "no longer", since the prompt writer never saw the earlier version.

Good image prompts usually lead with the medium and style, then structure and composition, then subject details, then lighting and colour, and close with a short line of identity-critical features that must survive. They match the reference's level of detail rather than adding to it, and they include nothing that is not in the references. GPT Image and Nano Banana respond best to clear natural-language descriptions with explicit constraints and positive phrasing, and when references are attached the prompt should say what each one is for ("use image 2 for the art style, image 3 for the character's face"). Where a model cannot take references, the prompt must carry the full style and likeness description in words. Encode such guidance in the system prompt only where this run shows it is missing.

This conversation continues across iterations, and log.md in your working directory holds every earlier round. Before changing anything, check whether a similar change was tried before and what happened: keep changes that helped, roll back or soften changes that made results worse (re-add a removed rule in its simplest form rather than restoring a long version), and do not repeat a fix that already failed. If the result is good and the feedback raises nothing the system prompt can fix, return it unchanged and say why; an unchanged prompt is a valid answer.

## Reply format

Reply in exactly this format and nothing else:

<analysis>
Images: what you took each image to be, by number.
Matches: what the result gets right.
Problems: each mismatch, ordered by impact, with the image numbers and concrete evidence.
Root causes: for each problem, the layer it belongs to and the exact cause, quoting the system prompt where relevant.
Changes: each edit to the system prompt, with what was wrong, what you changed, why, and your confidence (high, medium or low). Note anything you deliberately left alone, and any cause that lies outside the system prompt.
Check next time: the specific things the artist should look at in the next result to tell whether the changes worked.
</analysis>
<system_prompt>
The complete revised system prompt, ready to paste. No commentary inside this block.
</system_prompt>"""


def slugify(name):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-.")
    return slug or "prompt-coach"


def coach_root():
    try:
        import folder_paths

        base = folder_paths.get_output_directory()
    except ImportError:
        base = os.getcwd()
    return os.path.join(base, COACH_DIR)


def save_images(images, directory, prefix):
    """Saves every frame of every connected slot. Returns (slot number, relative path) pairs.

    Slot N becomes image_N.png; a batch on slot N becomes image_N_1.png, image_N_2.png..."""
    saved = []
    for slot in range(1, MAX_IMAGES + 1):
        tensor = images.get(f"image_{slot}")
        if tensor is None:
            continue
        batch = tensor if tensor.dim() == 4 else tensor.unsqueeze(0)
        for frame in range(batch.shape[0]):
            pil = tensor_to_pil(batch[frame])
            if pil is None:
                continue
            name = f"image_{slot}.png" if batch.shape[0] == 1 else f"image_{slot}_{frame + 1}.png"
            pil.convert("RGB").save(os.path.join(directory, name))
            saved.append((slot, f"{prefix}/{name}"))
    return saved


def build_message(iteration, system_prompt, brief, generated_prompt, image_model, saved, image_notes,
                  feedback, has_history):
    """The user message for one iteration. Everything Claude sees is in here or in the coach prompt."""
    parts = [f"# Iteration {iteration}"]
    parts.append(f"## System prompt under test\n\n{system_prompt.strip()}")
    if brief.strip():
        parts.append(f"## Brief / inputs given to the prompt writer\n\n{brief.strip()}")
    parts.append(f"## Prompt it generated\n\n{generated_prompt.strip() or '(not provided)'}")
    if image_model.strip():
        parts.append(f"## Image model the prompt was sent to\n\n{image_model.strip()}")
    if saved:
        listing = "\n".join(f"- image {slot}: `{path}`" for slot, path in saved)
        parts.append(
            "## Images\n\nRead each of these files before answering. The number is the image's "
            f"slot on the node, which is how the artist refers to it.\n\n{listing}"
        )
        parts.append(
            "## The artist's notes on the images\n\n"
            + (image_notes.strip() or "(none given; work out from the content which image is the result "
               "and which are references, and say what you assumed)")
        )
    else:
        parts.append("## Images\n\nNo images were connected this iteration.")
    parts.append(f"## The artist's feedback\n\n{feedback.strip() or '(no feedback given this time)'}")
    if has_history:
        parts.append(f"Earlier iterations are recorded in `{LOG_NAME}`.")
    return "\n\n".join(parts)


def parse_reply(text):
    def block(tag):
        match = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", text, re.DOTALL)
        return match.group(1).strip() if match else None

    new_prompt = block("system_prompt")
    if not new_prompt:
        raise RuntimeError(
            "Claude's reply had no <system_prompt> block, so there is no revised prompt to output. "
            f"Check that coach_system_prompt still asks for that format. Reply began: {text[:400]}"
        )
    return new_prompt, block("analysis") or ""


def append_log(path, iteration, session_name, message, analysis, new_prompt):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Prompt coach log: {session_name}\n\n")
    with open(path, "a", encoding="utf-8") as f:
        f.write(
            f"\n---\n\n<!-- iteration {iteration}, {stamp} -->\n\n{message}\n\n"
            f"## Claude's analysis\n\n{analysis}\n\n"
            f"## Revised system prompt (saved as system_prompt_v{iteration}.md)\n\n{new_prompt}\n"
        )


def run_claude(command, workdir, timeout_seconds):
    try:
        return subprocess.run(command, cwd=workdir, capture_output=True, text=True,
                              timeout=timeout_seconds, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude did not reply within {timeout_seconds}s. Raise timeout_seconds.")


class SFClaudePromptCoach(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="SFClaudePromptCoach",
            display_name="SF Claude Prompt Coach",
            category="Stillfront/LLM",
            description=(
                "Shows Claude a system prompt together with what it produced — the generated prompt, the "
                "reference images, the result and your feedback — and returns an improved system prompt. "
                "Runs on your Claude Code login and remembers earlier rounds of the same session."
            ),
            # Optional inputs render after required ones, so everything is required (with empty
            # defaults) to keep this top-to-bottom order.
            inputs=[
                IO.Autogrow.Input(
                    "images",
                    template=IO.Autogrow.TemplateNames(
                        IO.Image.Input("image"), names=[f"image_{i}" for i in range(1, MAX_IMAGES + 1)], min=0,
                    ),
                    tooltip="image 1: the generated result. image 2 and up: the references. A batch on one "
                    "slot becomes image_N_1, image_N_2, ...",
                ),
                IO.String.Input("system_prompt", multiline=True, default="",
                                tooltip="The system prompt you are tuning (the one the prompt-writing node used)."),
                IO.String.Input("generated_prompt", multiline=True, default="",
                                tooltip="The prompt that system prompt produced and sent to the image model."),
                IO.String.Input("feedback", multiline=True, default="",
                                placeholder="What's wrong with the result, in your words. Refer to images by "
                                "number, e.g. 'image 1 lost the thick outlines from image 2'.",
                                tooltip="Your feedback. Claude treats it as the most important input."),
                IO.String.Input("image_notes", multiline=True, default="",
                                placeholder="Optional. By default image 1 is the result and image 2+ are references.\n"
                                "image 2: style reference\nimage 3: character likeness reference",
                                tooltip="What each connected image is. The numbers match the image_N slots."),
                IO.String.Input("brief", multiline=True, default="",
                                placeholder="Optional: the brief the prompt writer was given (not instructions "
                                "for the coach).",
                                tooltip="The brief or other text inputs the prompt writer was given."),
                IO.String.Input("coach_system_prompt", multiline=True, default=DEFAULT_COACH_PROMPT,
                                tooltip="This node's own instructions to Claude, in full. Edit it here, or connect "
                                "your own text to override it; keep the <analysis>/<system_prompt> reply format."),
                IO.String.Input("session_name", default="prompt-coach",
                                tooltip="Rounds with the same name share Claude's memory and one log. "
                                "Change the name to start a fresh session."),
                IO.Combo.Input("model", options=MODEL_CHOICES, default="opus",
                               tooltip="Claude model. 'default' uses whatever Claude Code is set to."),
                IO.Int.Input("timeout_seconds", default=900, min=60, max=3600, step=30),
                IO.Int.Input("seed", default=0, min=0, max=0xFFFFFFFF, control_after_generate=True,
                             tooltip="Not sent to Claude. Change it to force a new round with identical inputs."),
                IO.String.Input("image_model", default="",
                                tooltip="Optional: which image model got the prompt, e.g. 'Nano Banana 2.1'."),
            ],
            outputs=[
                IO.String.Output("system_prompt", tooltip="The revised system prompt."),
                IO.String.Output("analysis", tooltip="What Claude saw, the root causes, and what it changed."),
                IO.String.Output("session_id", tooltip="Claude Code session id; `claude --resume <id>` "
                                 "continues it interactively from the log folder."),
                IO.String.Output("log_file", tooltip="Path of this session's log."),
            ],
        )

    @classmethod
    async def execute(cls, system_prompt, generated_prompt, feedback, image_notes, images, session_name,
                      brief="", image_model="", model="opus", coach_system_prompt=DEFAULT_COACH_PROMPT,
                      timeout_seconds=900, seed=0):
        if not system_prompt.strip():
            raise ValueError("system_prompt is empty — connect the system prompt you want to improve.")
        if not coach_system_prompt.strip():
            raise ValueError("coach_system_prompt is empty — it holds this node's instructions to Claude.")
        binary = find_claude_binary()
        if not binary:
            raise RuntimeError("Claude Code CLI not found. Install it from https://claude.com/claude-code, "
                               "sign in, then restart ComfyUI.")

        session_name = slugify(session_name)
        workdir = os.path.join(coach_root(), session_name)
        os.makedirs(workdir, exist_ok=True)
        session_path = os.path.join(workdir, SESSION_FILE)
        log_path = os.path.join(workdir, LOG_NAME)

        state = {}
        if os.path.exists(session_path):
            with open(session_path, encoding="utf-8") as f:
                state = json.load(f)
        iteration = state.get("iterations", 0) + 1

        iteration_dir = f"iteration_{iteration:03d}"
        os.makedirs(os.path.join(workdir, iteration_dir), exist_ok=True)
        saved = save_images(images or {}, os.path.join(workdir, iteration_dir), iteration_dir)

        message = build_message(iteration, system_prompt, brief, generated_prompt, image_model, saved,
                                image_notes, feedback, os.path.exists(log_path))

        def command(resume_id):
            cmd = [binary, "-p", message, "--output-format", "json",
                   "--system-prompt", coach_system_prompt, "--allowedTools", "Read"]
            if model != "default":
                cmd += ["--model", model]
            if resume_id:
                cmd += ["--resume", resume_id]
            return cmd

        resume_id = state.get("session_id")
        print(f"[SF Prompt Coach] '{session_name}' iteration {iteration}, {len(saved)} image(s), "
              f"{'resuming ' + resume_id if resume_id else 'new session'}.")
        completed = await asyncio.to_thread(run_claude, command(resume_id), workdir, timeout_seconds)

        note = ""
        if resume_id and completed.returncode != 0 and "No conversation found" in (completed.stderr + completed.stdout):
            # The Claude Code session was deleted; start a new one, which can still read the log.
            note = "(The previous Claude session could not be found, so this round started a new one.)\n\n"
            print("[SF Prompt Coach] Previous session not found; starting a new one.")
            completed = await asyncio.to_thread(run_claude, command(None), workdir, timeout_seconds)

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[:500]
            raise RuntimeError(f"Claude Code exited with code {completed.returncode}. {detail}")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"Could not parse Claude's response: {completed.stdout.strip()[:500]}")
        if payload.get("is_error"):
            raise RuntimeError(f"Claude reported an error: {payload.get('result', 'unknown')}")

        new_prompt, analysis = parse_reply(payload.get("result", ""))
        analysis = note + analysis
        session_id = payload.get("session_id", "")

        with open(os.path.join(workdir, f"system_prompt_v{iteration}.md"), "w", encoding="utf-8") as f:
            f.write(new_prompt + "\n")
        append_log(log_path, iteration, session_name, message, analysis, new_prompt)
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump({"session_id": session_id, "iterations": iteration}, f, indent=2)

        print(f"[SF Prompt Coach] Iteration {iteration} done in {payload.get('duration_ms', '?')}ms -> {log_path}")
        return IO.NodeOutput(new_prompt, analysis, session_id, log_path)


NODE_CLASS_MAPPINGS = {"SFClaudePromptCoach": SFClaudePromptCoach}
NODE_DISPLAY_NAME_MAPPINGS = {"SFClaudePromptCoach": "SF Claude Prompt Coach"}
