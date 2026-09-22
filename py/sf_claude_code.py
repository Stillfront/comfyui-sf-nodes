# ABOUTME: Runs a prompt through the locally installed Claude Code CLI, using its own login
# ABOUTME: Accepts text plus any number of images and returns Claude's reply as a string

import json
import os
import shutil
import subprocess
import tempfile

from .vertexai_utils import tensor_to_pil

MAX_IMAGES = 16

# Aliases rather than pinned model IDs, so this keeps working as models are updated.
MODEL_CHOICES = ["default", "opus", "sonnet", "haiku"]

BINARY_CANDIDATES = [
    "~/.local/bin/claude",
    "~/.claude/local/claude",
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
]


def find_claude_binary():
    """Locates the Claude Code CLI, which may not be on ComfyUI's PATH."""
    found = shutil.which("claude")
    if found:
        return found
    for candidate in BINARY_CANDIDATES:
        path = os.path.expanduser(candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def save_images(image_inputs, directory):
    """Writes every frame of every connected IMAGE input to disk. Returns filenames."""
    names = []
    for slot, tensor in image_inputs:
        if tensor is None:
            continue
        batch = tensor if tensor.dim() == 4 else tensor.unsqueeze(0)
        for frame in range(batch.shape[0]):
            pil = tensor_to_pil(batch[frame])
            if pil is None:
                continue
            name = f"image_{slot}.png" if batch.shape[0] == 1 else f"image_{slot}_{frame + 1}.png"
            pil.convert("RGB").save(os.path.join(directory, name))
            names.append(name)
    return names


def build_prompt(prompt, image_names):
    """Prefixes the request with instructions to read the images off disk."""
    if not image_names:
        return prompt

    listing = ", ".join(image_names)
    plural = "image" if len(image_names) == 1 else "images"
    return (
        f"The following {plural} are in your current working directory: {listing}\n"
        f"Use the Read tool on each of them first, then respond to this request:\n\n"
        f"{prompt}"
    )


class SFClaudeCode:
    """
    Sends a prompt (and any attached images) to Claude through the Claude Code
    CLI installed on this machine, so it runs on your existing Claude login
    rather than a separate API key.

    Connect an image and another image slot appears automatically.
    """

    @classmethod
    def INPUT_TYPES(cls):
        optional = {
            f"image_{i}": ("IMAGE",) for i in range(1, MAX_IMAGES + 1)
        }
        return {
            "required": {
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "What you want Claude to do.",
                    },
                ),
                "system_prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": (
                            "Extra instructions shaping how Claude responds, e.g. "
                            "'Reply with only the prompt text, no preamble.' Leave blank to skip."
                        ),
                    },
                ),
                "model": (
                    MODEL_CHOICES,
                    {
                        "default": "default",
                        "tooltip": "Which Claude model to use. 'default' uses whatever Claude Code is set to.",
                    },
                ),
                "timeout_seconds": (
                    "INT",
                    {
                        "default": 300,
                        "min": 30,
                        "max": 3600,
                        "step": 30,
                        "tooltip": "Give up if Claude has not replied within this long.",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFF,
                        "control_after_generate": True,
                        "tooltip": (
                            "Not sent to Claude. Change it to force a fresh reply instead "
                            "of reusing ComfyUI's cached result."
                        ),
                    },
                ),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "run"
    CATEGORY = "Stillfront/LLM"

    DESCRIPTION = """
Sends text and images to Claude via the **Claude Code CLI** on this machine,
using your existing Claude login — no API key needed.

Requires Claude Code to be installed and signed in on whichever computer runs
ComfyUI. Connect an image and a further image slot appears automatically.

Change **seed** to force a fresh reply; otherwise ComfyUI reuses the cached one.
"""

    def run(self, prompt, system_prompt, model, timeout_seconds, seed, **kwargs):
        if not prompt.strip():
            raise ValueError("prompt is empty — give Claude something to do.")

        binary = find_claude_binary()
        if not binary:
            raise RuntimeError(
                "Claude Code CLI not found. Install it from "
                "https://claude.com/claude-code and sign in, then restart ComfyUI."
            )

        image_inputs = [
            (i, kwargs.get(f"image_{i}"))
            for i in range(1, MAX_IMAGES + 1)
            if kwargs.get(f"image_{i}") is not None
        ]

        workdir = tempfile.mkdtemp(prefix="sf_claude_")
        try:
            image_names = save_images(image_inputs, workdir)

            command = [
                binary,
                "-p",
                build_prompt(prompt, image_names),
                "--output-format",
                "json",
            ]
            if system_prompt.strip():
                command += ["--append-system-prompt", system_prompt.strip()]
            if model != "default":
                command += ["--model", model]
            if image_names:
                command += ["--allowedTools", "Read"]

            print(
                f"[SF Claude Code] Running {model} with {len(image_names)} image(s), "
                f"timeout {timeout_seconds}s."
            )

            try:
                completed = subprocess.run(
                    command,
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    # Without this the CLI spends 3s waiting on stdin it will never get.
                    stdin=subprocess.DEVNULL,
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(
                    f"Claude did not reply within {timeout_seconds}s. Raise timeout_seconds "
                    f"or simplify the request."
                )

            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()[:500]
                raise RuntimeError(
                    f"Claude Code exited with code {completed.returncode}. {detail}"
                )

            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"Could not parse Claude's response: {completed.stdout.strip()[:500]}"
                )

            if payload.get("is_error"):
                raise RuntimeError(
                    f"Claude reported an error: {payload.get('result', 'unknown')}"
                )

            text = payload.get("result", "")
            if not text:
                raise RuntimeError("Claude returned an empty response.")

            print(
                f"[SF Claude Code] Got {len(text)} characters in "
                f"{payload.get('duration_ms', '?')}ms."
            )
            return (text,)

        finally:
            shutil.rmtree(workdir, ignore_errors=True)


NODE_CLASS_MAPPINGS = {"SFClaudeCode": SFClaudeCode}
NODE_DISPLAY_NAME_MAPPINGS = {"SFClaudeCode": "SF Claude Code"}
