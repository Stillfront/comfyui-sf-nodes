# ABOUTME: Claude picks reference images from an asset library and writes the prompt for them
# ABOUTME: Reads a manifest describing the assets; looking at the images themselves is optional

import json
import os
import re
import subprocess
import tempfile

import numpy as np
import torch
from PIL import Image

from .sf_claude_code import MODEL_CHOICES, find_claude_binary

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
MAX_LISTED = 2000


def scan_library(root, recursive):
    """Image files under `root`, as paths relative to it, in sorted order."""
    found = []
    if recursive:
        for folder, _, names in os.walk(root):
            for name in names:
                if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                    full = os.path.join(folder, name)
                    found.append(os.path.relpath(full, root))
    else:
        for name in os.listdir(root):
            if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                found.append(name)
    return sorted(found)[:MAX_LISTED]


def read_manifest(root, manifest):
    """The asset descriptions file, or None when there isn't one."""
    name = (manifest or "").strip()
    if not name:
        return None
    path = os.path.join(root, name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return None


def build_request(system_prompt, instruction, files, manifest_text, max_images, may_look):
    """The single prompt sent to Claude."""
    parts = []
    if system_prompt.strip():
        parts.append(system_prompt.strip())

    if manifest_text:
        parts.append(
            "Here is the asset library manifest describing what each file contains:\n\n"
            f"{manifest_text.strip()}"
        )

    listing = "\n".join(f"  {name}" for name in files)
    parts.append(f"These are the image files available ({len(files)} total):\n{listing}")

    if may_look:
        parts.append(
            "You may use the Read tool on any of these files to look at them before "
            "deciding. They are in your current working directory."
        )

    parts.append(f"Request:\n{instruction.strip()}")
    parts.append(
        f"Choose at most {max_images} file(s). Reply with ONLY a JSON object and nothing "
        f"else — no explanation, no code fence:\n"
        f'{{"files": ["exact/path/as/listed.png"], "prompt": "the image generation prompt"}}\n'
        f"Use file paths exactly as they appear in the listing. The prompt should refer to "
        f"the chosen images in the order you list them."
    )
    return "\n\n".join(parts)


def parse_reply(text):
    """The JSON object out of Claude's reply, tolerating a code fence around it."""
    stripped = text.strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        raise RuntimeError(f"Claude did not return JSON. It said: {stripped[:300]}")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude's JSON could not be parsed ({e}): {stripped[:300]}")

    files = payload.get("files") or []
    prompt = str(payload.get("prompt") or "").strip()
    if not isinstance(files, list):
        raise RuntimeError("Claude's 'files' field was not a list.")
    return [str(f).strip() for f in files if str(f).strip()], prompt


def resolve_picks(picked, available, root):
    """Map Claude's filenames onto real paths, matching on basename as a fallback."""
    by_rel = {name: name for name in available}
    by_base = {}
    for name in available:
        by_base.setdefault(os.path.basename(name).lower(), name)

    resolved, missing = [], []
    for want in picked:
        cleaned = want.strip().lstrip("./")
        match = by_rel.get(cleaned) or by_base.get(os.path.basename(cleaned).lower())
        if match:
            resolved.append(os.path.join(root, match))
        else:
            missing.append(want)
    return resolved, missing


def to_image_batch(paths, pad_to_fit):
    """Load the images into one ComfyUI IMAGE tensor.

    A batch is a single tensor, so every frame must share dimensions. With
    `pad_to_fit` each image is scaled to fit and centred on a common canvas,
    which keeps its aspect ratio; without it they are stretched to match.
    """
    images = [Image.open(p).convert("RGB") for p in paths]
    width = max(im.width for im in images)
    height = max(im.height for im in images)

    frames = []
    for im in images:
        if pad_to_fit:
            scale = min(width / im.width, height / im.height)
            size = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
            canvas = Image.new("RGB", (width, height), (0, 0, 0))
            canvas.paste(im.resize(size, Image.LANCZOS),
                         ((width - size[0]) // 2, (height - size[1]) // 2))
            im = canvas
        else:
            im = im.resize((width, height), Image.LANCZOS)
        frames.append(np.asarray(im, dtype=np.float32) / 255.0)

    return torch.from_numpy(np.stack(frames))


class SFClaudeAssetDirector:
    """
    Claude picks reference images out of an asset library and writes the prompt
    that goes with them.

    Decisions are made from a manifest describing the assets, so the library can
    be large without every run costing a pile of image reads. Outputs an IMAGE
    batch and a STRING, which wire straight into an image generation node.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "library_path": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                        "tooltip": (
                            "Folder holding the assets. For Google Drive, point this at "
                            "your Drive for Desktop sync folder."
                        ),
                    },
                ),
                "manifest": (
                    "STRING",
                    {
                        "default": "assets.json",
                        "tooltip": (
                            "File inside the library describing each asset, used to choose "
                            "between them. Any text or JSON format. Ignored if absent."
                        ),
                    },
                ),
                "system_prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Standing instructions — how to choose, how to write the prompt.",
                    },
                ),
                "instruction": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": (
                            "What you want this run. Type it here or wire a string in, "
                            "e.g. 'Make a poster. Pick the characters you think work best.'"
                        ),
                    },
                ),
                "max_images": (
                    "INT",
                    {
                        "default": 5,
                        "min": 1,
                        "max": 20,
                        "step": 1,
                        "tooltip": "Most reference images Claude may choose.",
                    },
                ),
                "pad_to_fit": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "On: scale each image to fit a shared canvas and centre it, "
                            "keeping aspect ratios. Off: stretch them all to one size."
                        ),
                    },
                ),
                "look_at_images": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": (
                            "Let Claude open the image files as well as the manifest. "
                            "Better choices on an unlabelled library, but roughly 5 "
                            "seconds per image it opens."
                        ),
                    },
                ),
                "recursive": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "Include images in subfolders."},
                ),
                "model": (
                    MODEL_CHOICES,
                    {"default": "default", "tooltip": "Which Claude model decides."},
                ),
                "timeout_seconds": (
                    "INT",
                    {"default": 300, "min": 30, "max": 3600, "step": 30,
                     "tooltip": "Give up if Claude has not replied within this long."},
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFF,
                        "control_after_generate": True,
                        "tooltip": (
                            "Not sent to Claude. Change it to force a fresh choice instead "
                            "of reusing ComfyUI's cached result."
                        ),
                    },
                ),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("images", "prompt", "picked")
    FUNCTION = "direct"
    CATEGORY = "Stillfront/LLM"

    DESCRIPTION = """
Claude reads your asset library's **manifest**, chooses which references suit the
request, and writes the image prompt to go with them.

Outputs an IMAGE batch and the prompt, ready to wire into Nano Banana or any
other generation node. Point **library_path** at a Google Drive for Desktop sync
folder to work straight off Drive.

**look_at_images** is off by default: choices come from the manifest, so a large
library costs nothing extra. Turn it on to have Claude open the files too.
"""

    def direct(self, library_path, manifest, system_prompt, instruction, max_images,
               pad_to_fit, look_at_images, recursive, model, timeout_seconds, seed):
        root = os.path.expanduser(library_path.strip())
        if not root or not os.path.isdir(root):
            raise ValueError(f"library_path is not a folder: {library_path!r}")
        if not instruction.strip():
            raise ValueError("instruction is empty — tell Claude what this run is for.")

        binary = find_claude_binary()
        if not binary:
            raise RuntimeError(
                "Claude Code CLI not found. Install it from https://claude.com/claude-code "
                "and sign in, then restart ComfyUI."
            )

        files = scan_library(root, recursive)
        if not files:
            raise ValueError(f"No image files found in {root}")

        manifest_text = read_manifest(root, manifest)
        if manifest_text is None and manifest.strip():
            print(
                f"[SF Claude Asset Director] No manifest '{manifest.strip()}' in the library; "
                f"choosing from filenames alone."
            )

        request = build_request(
            system_prompt, instruction, files, manifest_text, max_images, look_at_images
        )

        command = [binary, "-p", request, "--output-format", "json"]
        if model != "default":
            command += ["--model", model]
        if look_at_images:
            command += ["--allowedTools", "Read"]

        print(
            f"[SF Claude Asset Director] {len(files)} asset(s), "
            f"manifest={'yes' if manifest_text else 'no'}, vision={'on' if look_at_images else 'off'}."
        )

        try:
            completed = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Claude did not reply within {timeout_seconds}s. Raise timeout_seconds, "
                f"or turn look_at_images off."
            )

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[:500]
            raise RuntimeError(f"Claude Code exited with code {completed.returncode}. {detail}")

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"Unreadable response: {completed.stdout.strip()[:400]}")

        if payload.get("is_error"):
            raise RuntimeError(f"Claude reported an error: {payload.get('result', 'unknown')}")

        picked, prompt = parse_reply(payload.get("result", ""))
        if not picked:
            raise RuntimeError("Claude chose no images. Check the manifest describes the assets.")
        if not prompt:
            raise RuntimeError("Claude returned no prompt.")

        paths, missing = resolve_picks(picked[:max_images], files, root)
        if missing:
            print(f"[SF Claude Asset Director] Ignoring names not in the library: {missing}")
        if not paths:
            raise RuntimeError(
                f"None of Claude's choices matched a real file. It asked for: {picked}"
            )

        batch = to_image_batch(paths, pad_to_fit)
        names = [os.path.relpath(p, root) for p in paths]
        print(f"[SF Claude Asset Director] Chose {len(names)}: {', '.join(names)}")

        return (batch, prompt, "\n".join(names))


NODE_CLASS_MAPPINGS = {"SFClaudeAssetDirector": SFClaudeAssetDirector}
NODE_DISPLAY_NAME_MAPPINGS = {"SFClaudeAssetDirector": "SF Claude Asset Director"}
