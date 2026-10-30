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

DEFAULT_COACH_PROMPT = """You are a prompt engineer coaching a system prompt for a game-art pipeline.

In that pipeline an LLM (the "prompt writer") is given the SYSTEM PROMPT UNDER TEST plus a brief, and
sometimes an asset library. It writes a prompt for an image generation model and may pick reference
images to send with it. The image model then produces the RESULT. The artist wants the result to copy
the art style of the references, keep character likeness where relevant, and follow the brief.

Each message you receive is one iteration and contains:
- The system prompt under test.
- The brief / inputs the prompt writer was given (if provided).
- The prompt it generated, and the image model it was sent to (if provided).
- Numbered images saved in your working directory, with the artist's notes on what each one is.
  Always use the Read tool to look at every listed image before you answer. Refer to images by the
  same numbers the artist uses ("image 1", "image 2", ...).
- The artist's feedback on the result.

Your job:
1. Look at the result next to the references. Compare art style (rendering, line work, shading,
   palette, texture, level of detail), character likeness, proportions, composition, and anything the
   brief asked for. Say concretely what matches and what does not.
2. Judge the generated prompt: did it describe the references' style and the subject precisely enough
   for this image model? Did it pick or describe the right references?
3. Trace each problem back to the system prompt under test: a missing rule, an ambiguous instruction,
   wrong priorities, too little guidance on describing style or choosing references, or an instruction
   that pushes the prompt writer the wrong way.
4. Treat the artist's feedback as the highest-priority signal. If what you see disagrees with it, say
   so, but follow the artist.
5. Revise the system prompt. Keep everything that works, keep its structure and tone, and make
   targeted changes that fix the root causes. Rules must generalise to future briefs and assets; do
   not hard-code details of this one asset unless the artist asks for that.

This conversation continues across iterations. Use what you learned in earlier ones: keep changes that
helped, undo changes that made results worse, and do not repeat a fix that already failed. A log of
earlier iterations is in log.md in your working directory; Read it if you need detail you no longer
remember. Images from earlier iterations are kept in their iteration folders.

Reply in exactly this format and nothing else:

<analysis>
- What the result gets right and wrong, referring to images by number.
- The root cause of each problem in the system prompt under test.
- Each change you made and why.
- What the artist should check in the next iteration.
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
            inputs=[
                IO.String.Input("system_prompt", multiline=True, default="",
                                tooltip="The system prompt you are tuning (the one the prompt-writing node used)."),
                IO.String.Input("generated_prompt", multiline=True, default="",
                                tooltip="The prompt that system prompt produced and sent to the image model."),
                IO.String.Input("feedback", multiline=True, default="",
                                placeholder="What's wrong with the result, in your words. Refer to images by "
                                "number, e.g. 'image 1 lost the thick outlines from image 2'.",
                                tooltip="Your feedback. Claude treats it as the most important input."),
                IO.String.Input("image_notes", multiline=True, default="",
                                placeholder="image 1: the result from Nano Banana\nimage 2: style reference\n"
                                "image 3: character likeness reference",
                                tooltip="What each connected image is. The numbers match the image_N slots."),
                IO.Autogrow.Input(
                    "images",
                    template=IO.Autogrow.TemplateNames(
                        IO.Image.Input("image"), names=[f"image_{i}" for i in range(1, MAX_IMAGES + 1)], min=0,
                    ),
                    tooltip="The result and the reference images. A batch on one slot becomes image_N_1, "
                    "image_N_2, ...",
                ),
                IO.String.Input("session_name", default="prompt-coach",
                                tooltip="Rounds with the same name share Claude's memory and one log. "
                                "Change the name to start a fresh session."),
                IO.String.Input("brief", multiline=True, default="", optional=True,
                                tooltip="Optional: the brief or other text inputs the prompt writer was given."),
                IO.String.Input("image_model", default="", optional=True,
                                tooltip="Optional: which image model got the prompt, e.g. 'Nano Banana 2.1'."),
                IO.Combo.Input("model", options=MODEL_CHOICES, default="opus",
                               tooltip="Claude model. 'default' uses whatever Claude Code is set to."),
                IO.String.Input("coach_system_prompt", multiline=True, default=DEFAULT_COACH_PROMPT,
                                advanced=True,
                                tooltip="This node's own instructions to Claude, in full. Edit freely, but keep "
                                "the <analysis>/<system_prompt> reply format."),
                IO.Int.Input("timeout_seconds", default=900, min=60, max=3600, step=30, advanced=True),
                IO.Int.Input("seed", default=0, min=0, max=0xFFFFFFFF, control_after_generate=True, advanced=True,
                             tooltip="Not sent to Claude. Change it to force a new round with identical inputs."),
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
