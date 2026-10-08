# ABOUTME: Claude surveys a folder of game assets and writes a searchable manifest for it
# ABOUTME: Can optionally reorganise and rename the files; read-only by default

import json
import os
import re
import shutil
import subprocess
import time

from .sf_claude_code import MODEL_CHOICES, find_claude_binary

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tga"}

MODE_MANIFEST = "manifest only (read-only)"
MODE_COPY = "organise into a copy"
MODE_IN_PLACE = "organise in place"
MODES = [MODE_MANIFEST, MODE_COPY, MODE_IN_PLACE]

SCHEMA_VERSION = "sf-asset-library/1"

# What the manifest has to contain for SF Claude Asset Director to search it well:
# one flat list (cheaper to scan than a tree), the same keys on every entry, a
# one-sentence description carrying the meaning, and a project-level art style so
# generated prompts stay consistent across the whole library.
SCHEMA_SPEC = """{
  "schema": "sf-asset-library/1",
  "project": "<short project name>",
  "art_style": "<one sentence describing the shared visual style of the whole library>",
  "generated": "<YYYY-MM-DD>",
  "assets": [
    {
      "file": "<path relative to the library root, exactly as it exists on disk>",
      "name": "<short human name>",
      "category": "<character|environment|prop|ui|vfx|other>",
      "subcategory": "<hero|enemy|npc|location|background|weapon|icon|...>",
      "archetype": "<for characters: tank|healer|rogue|mage|boss|minion|... else omit>",
      "tags": ["<lowercase keyword>", "..."],
      "desc": "<one sentence: what it depicts, pose/view, dominant colours>"
    }
  ]
}"""

DEFAULT_SYSTEM_PROMPT = """You are cataloguing a game asset library.

Judge each asset on what it depicts and what role it would play in a game.
Keep `desc` to one sentence that would let someone pick this asset without
seeing it. Make `tags` lowercase, specific and useful for searching — subject,
colour, pose, view angle, mood. Prefer a small shared vocabulary across the
library over inventing a new word per asset."""


def scan_assets(root):
    """Image files under `root`, relative to it."""
    found = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                found.append(os.path.relpath(os.path.join(folder, name), root))
    return sorted(found)


def extract_json(text):
    """The JSON object out of a reply that may be fenced or prefaced."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise RuntimeError(f"Claude did not return JSON. It said: {text.strip()[:300]}")
    body = text[start : end + 1]
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude's JSON could not be parsed ({e}): {body[:300]}")


def build_instruction(mode, assets, project_notes, manifest_name, write_manifest, out_dir):
    """The task description handed to Claude."""
    parts = [
        f"You are building an asset library manifest for {len(assets)} image file(s)."
    ]

    if project_notes.strip():
        parts.append(f"About this project:\n{project_notes.strip()}")

    listing = "\n".join(f"  {name}" for name in assets)
    parts.append(f"The files, relative to your working directory:\n{listing}")

    parts.append(
        "Open each image with the Read tool before describing it. Work through them "
        "steadily; do not guess from a filename."
    )

    if mode == MODE_MANIFEST:
        parts.append(
            "Do NOT move, rename, copy or delete anything. This is a survey only."
        )
        if write_manifest:
            parts.append(
                f"When you have seen them all, write the manifest to `{manifest_name}` "
                f"in the working directory using the Write tool, then reply with the "
                f"word DONE and nothing else."
            )
        else:
            parts.append(
                "When you have seen them all, reply with ONLY the manifest JSON — no "
                "commentary, no code fence."
            )
    else:
        where = (
            f"a new folder at `{out_dir}`, leaving the originals untouched"
            if mode == MODE_COPY
            else "the working directory itself"
        )
        parts.append(
            f"Then reorganise the library into {where}:\n"
            f"- Group files into folders by category, e.g. characters/heroes, "
            f"characters/enemies, environments, props, ui, vfx.\n"
            f"- Rename to lowercase_with_underscores, descriptive of the subject, no "
            f"spaces and no version noise. Keep the original extension.\n"
            f"- Never discard a file. Every input must end up somewhere.\n"
            f"- Use Bash (cp for a copy, mv in place) to do the moving."
        )
        parts.append(
            f"The `file` field of every asset must be the path AFTER reorganising, "
            f"relative to the library root. Write the manifest to `{manifest_name}` at "
            f"the root of the reorganised library, then reply with the word DONE and "
            f"nothing else."
        )

    parts.append(f"The manifest must match this shape exactly:\n{SCHEMA_SPEC}")
    return "\n\n".join(parts)


class SFClaudeLibraryBuilder:
    """
    Surveys a folder of game assets and writes a manifest describing each one,
    so SF Claude Asset Director can choose between them without opening images.

    Read-only by default. It can also reorganise and rename the files, into a
    copy or in place, when you ask it to.
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
                        "tooltip": "Folder holding the assets to catalogue.",
                    },
                ),
                "mode": (
                    MODES,
                    {
                        "default": MODE_MANIFEST,
                        "tooltip": (
                            "manifest only: nothing is moved or renamed. "
                            "organise into a copy: originals untouched, tidy copy written "
                            "to output_path. organise in place: renames and moves your "
                            "actual files."
                        ),
                    },
                ),
                "output_path": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                        "tooltip": "Destination folder, for 'organise into a copy' only.",
                    },
                ),
                "project_notes": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": (
                            "What the game is, and anything Claude could not infer from "
                            "the images — genre, art direction, naming you prefer."
                        ),
                    },
                ),
                "system_prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": DEFAULT_SYSTEM_PROMPT,
                        "tooltip": "How to categorise and describe. Edit to suit your project.",
                    },
                ),
                "manifest_name": (
                    "STRING",
                    {
                        "default": "manifest.json",
                        "tooltip": "Filename for the manifest, written at the library root.",
                    },
                ),
                "write_manifest": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": (
                            "Off: the manifest is only returned as text for you to read "
                            "and save yourself. On: it is written into the library."
                        ),
                    },
                ),
                "model": (
                    MODEL_CHOICES,
                    {"default": "default", "tooltip": "Which Claude model does the cataloguing."},
                ),
                "timeout_seconds": (
                    "INT",
                    {
                        "default": 1800,
                        "min": 60,
                        "max": 7200,
                        "step": 60,
                        "tooltip": (
                            "Allow roughly 5 seconds per asset. 100 assets needs about "
                            "10 minutes."
                        ),
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFF,
                        "control_after_generate": True,
                        "tooltip": "Not sent to Claude. Change it to force a fresh run.",
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("manifest", "report")
    FUNCTION = "build"
    CATEGORY = "Stillfront/LLM"

    DESCRIPTION = """
Claude looks at every asset in a folder and writes a manifest describing each —
category, archetype, tags and a one-line description — plus a project-level art
style. **SF Claude Asset Director** then searches that manifest instead of
opening images.

Defaults to **manifest only**, which touches nothing: you get the JSON as text to
read and save yourself. Switch `write_manifest` on to have it saved into the
library, or change `mode` to let Claude reorganise and rename the files too.

Budget about 5 seconds per asset — it opens every image.
"""

    def build(self, library_path, mode, output_path, project_notes, system_prompt,
              manifest_name, write_manifest, model, timeout_seconds, seed):
        root = os.path.expanduser(library_path.strip())
        if not root or not os.path.isdir(root):
            raise ValueError(f"library_path is not a folder: {library_path!r}")

        out_dir = os.path.expanduser(output_path.strip())
        if mode == MODE_COPY:
            if not out_dir:
                raise ValueError("output_path is required for 'organise into a copy'.")
            if os.path.abspath(out_dir).startswith(os.path.abspath(root) + os.sep):
                raise ValueError("output_path must sit outside library_path.")
            os.makedirs(out_dir, exist_ok=True)

        binary = find_claude_binary()
        if not binary:
            raise RuntimeError(
                "Claude Code CLI not found. Install it from https://claude.com/claude-code "
                "and sign in, then restart ComfyUI."
            )

        assets = scan_assets(root)
        if not assets:
            raise ValueError(f"No image files found in {root}")

        writes_file = write_manifest or mode != MODE_MANIFEST
        tools = "Read" if mode == MODE_MANIFEST and not write_manifest else "Read,Write,Bash"

        command = [
            binary,
            "-p",
            build_instruction(mode, assets, project_notes, manifest_name,
                              writes_file, out_dir),
            "--output-format",
            "json",
            "--allowedTools",
            tools,
        ]
        if system_prompt.strip():
            command += ["--append-system-prompt", system_prompt.strip()]
        if model != "default":
            command += ["--model", model]

        print(
            f"[SF Claude Library Builder] Cataloguing {len(assets)} asset(s) — mode='{mode}', "
            f"tools={tools}. This opens every image, so allow time."
        )
        started = time.time()

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
                f"Claude did not finish within {timeout_seconds}s. Raise timeout_seconds "
                f"(about 5s per asset) or catalogue a smaller folder."
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

        elapsed = time.time() - started
        reply = payload.get("result", "")

        # When Claude wrote the file, read it back; otherwise its reply IS the manifest.
        manifest_root = out_dir if mode == MODE_COPY else root
        manifest_path = os.path.join(manifest_root, manifest_name)

        if writes_file:
            if not os.path.isfile(manifest_path):
                raise RuntimeError(
                    f"Claude was asked to write {manifest_name} but it is not there. "
                    f"It replied: {reply.strip()[:300]}"
                )
            with open(manifest_path, encoding="utf-8") as f:
                manifest_text = f.read()
        else:
            manifest_text = json.dumps(extract_json(reply), indent=2)

        data = extract_json(manifest_text)
        entries = data.get("assets") or []
        counts = {}
        for entry in entries:
            counts[entry.get("category", "?")] = counts.get(entry.get("category", "?"), 0) + 1

        report = "\n".join([
            f"mode:        {mode}",
            f"scanned:     {len(assets)} file(s) in {root}",
            f"catalogued:  {len(entries)} asset(s)",
            f"categories:  " + (", ".join(f"{k} x{v}" for k, v in sorted(counts.items())) or "none"),
            f"art style:   {data.get('art_style', '(not set)')}",
            f"manifest:    " + (manifest_path if writes_file else "returned as text, not saved"),
            f"took:        {elapsed:.0f}s",
        ])
        print(f"[SF Claude Library Builder] {len(entries)} asset(s) catalogued in {elapsed:.0f}s.")

        if len(entries) < len(assets):
            report += f"\nWARNING:     {len(assets) - len(entries)} file(s) were not catalogued."

        return (manifest_text, report)


NODE_CLASS_MAPPINGS = {"SFClaudeLibraryBuilder": SFClaudeLibraryBuilder}
NODE_DISPLAY_NAME_MAPPINGS = {"SFClaudeLibraryBuilder": "SF Claude Library Builder"}
