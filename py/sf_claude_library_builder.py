# ABOUTME: Claude surveys a folder of game assets and writes a searchable manifest for it
# ABOUTME: Processes assets in small batches with a resumable checkpoint, so a failure costs little

import hashlib
import json
import os
import subprocess
import tempfile
import time

from .sf_claude_code import MODEL_CHOICES, find_claude_binary

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tga"}

MODE_MANIFEST = "manifest only (read-only)"
MODE_COPY = "organise into a copy"
MODE_IN_PLACE = "organise in place"
MODES = [MODE_MANIFEST, MODE_COPY, MODE_IN_PLACE]

SCHEMA_VERSION = "sf-asset-library/1"
CHECKPOINT_NAME = ".sf_library_builder_checkpoint.json"

ASSET_SCHEMA_SPEC = """{
  "file": "<path relative to the library root, exactly as it exists on disk>",
  "name": "<short human name>",
  "category": "<character|environment|prop|ui|vfx|other>",
  "subcategory": "<hero|enemy|npc|location|background|weapon|icon|...>",
  "archetype": "<for characters: tank|healer|rogue|mage|boss|minion|... else omit>",
  "tags": ["<lowercase keyword>", "..."],
  "desc": "<one sentence: what it depicts, pose/view, dominant colours>"
}"""

DEFAULT_SYSTEM_PROMPT = """You are cataloguing a game asset library.

Judge each asset on what it depicts and what role it would play in a game.
Keep `desc` to one sentence that would let someone pick this asset without
seeing it. Make `tags` lowercase, specific and useful for searching — subject,
colour, pose, view angle, mood. Prefer a small shared vocabulary across the
library over inventing a new word per asset."""


def scan_assets(root):
    """Image files under `root`, relative to it, in a stable sorted order."""
    found = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                found.append(os.path.relpath(os.path.join(folder, name), root))
    return sorted(found)


def chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


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


def canonicalize(claude_path, expected):
    """Map Claude's returned file path onto one of the paths we actually asked
    about, tolerating a leading './' or a basename-only answer."""
    cleaned = (claude_path or "").strip().lstrip("./")
    if cleaned in expected:
        return cleaned
    base = os.path.basename(cleaned).lower()
    for candidate in expected:
        if os.path.basename(candidate).lower() == base:
            return candidate
    return cleaned


def checkpoint_key(mode, manifest_name, system_prompt, project_notes, all_files):
    """A fingerprint of this exact job, so a checkpoint only resumes a matching rerun."""
    payload = json.dumps(
        {
            "mode": mode,
            "manifest_name": manifest_name,
            "system_prompt": system_prompt,
            "project_notes": project_notes,
            "files": all_files,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_checkpoint(root, key):
    path = os.path.join(root, CHECKPOINT_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if data.get("key") == key else None


def save_checkpoint(root, key, project, art_style, done_assets):
    """Atomic write, so a crash mid-save can't corrupt the checkpoint."""
    path = os.path.join(root, CHECKPOINT_NAME)
    data = {"key": key, "project": project, "art_style": art_style, "done_assets": done_assets}
    fd, tmp = tempfile.mkstemp(dir=root, prefix=".sf_checkpoint_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def clear_checkpoint(root):
    path = os.path.join(root, CHECKPOINT_NAME)
    if os.path.isfile(path):
        os.remove(path)


def build_batch_instruction(mode, batch_files, total_count, project_notes, established, out_dir):
    """The task description for ONE batch call — scoped to just its own files."""
    parts = [
        f"You are cataloguing {len(batch_files)} file(s) from one batch of a "
        f"{total_count}-file game asset library. You only need to handle the "
        f"files listed below — nothing else exists from your point of view."
    ]

    if project_notes.strip():
        parts.append(f"About this project:\n{project_notes.strip()}")

    listing = "\n".join(f"  {name}" for name in batch_files)
    parts.append(f"Your files for this batch:\n{listing}")

    parts.append(
        "Open each one with the Read tool before describing it. Work through them "
        "steadily; do not guess from a filename."
    )

    if mode == MODE_MANIFEST:
        parts.append("Do NOT move, rename, copy or delete anything. This is a survey only.")
    else:
        where = (
            f"a new folder at `{out_dir}`, leaving the originals untouched"
            if mode == MODE_COPY
            else "the working directory itself"
        )
        parts.append(
            f"Then reorganise ONLY these files into {where}:\n"
            f"- Group by category, e.g. characters/heroes, characters/enemies, "
            f"environments, props, ui, vfx.\n"
            f"- Rename to lowercase_with_underscores, descriptive of the subject, "
            f"no spaces, no version noise. Keep the original extension.\n"
            f"- Never discard a file.\n"
            f"- Use Bash (cp for a copy, mv in place) to do the moving.\n"
            f"The `file` field of each asset must be its path AFTER reorganising, "
            f"relative to the library root."
        )

    if established:
        project, art_style = established
        parts.append(
            f"This library's project name and art style are already settled by an "
            f"earlier batch — reuse them exactly, do not invent new ones:\n"
            f'  project: "{project}"\n  art_style: "{art_style}"'
        )
        parts.append(
            f"Reply with ONLY a JSON object of this shape — no commentary, no code "
            f"fence, no other top-level keys:\n"
            f'{{"assets": [{ASSET_SCHEMA_SPEC}]}}\n'
            f"The assets array must contain exactly one entry per file listed above."
        )
    else:
        parts.append(
            f"You are establishing this library's project name and art style for "
            f"the first time — later batches will reuse whatever you choose here, "
            f"so make `art_style` a precise sentence covering the whole library's "
            f"visual approach, not just these files.\n"
            f"Reply with ONLY a JSON object of this shape — no commentary, no code "
            f"fence:\n"
            f'{{"project": "<short project name>", "art_style": "<one sentence>", '
            f'"assets": [{ASSET_SCHEMA_SPEC}]}}\n'
            f"The assets array must contain exactly one entry per file listed above."
        )

    return "\n\n".join(parts)


class SFClaudeLibraryBuilder:
    """
    Surveys a folder of game assets and writes a manifest describing each one,
    so SF Claude Asset Director can choose between them without opening images.

    Processes assets in small batches rather than one session, because a single
    session covering a large library can blow up in turns and cost with nothing
    to show for it. A checkpoint records finished batches, so a failed or
    interrupted run resumes instead of re-paying for work already done.

    Read-only by default. It can also reorganise and rename the files, into a
    copy or in place, when you ask it to.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "library_path": (
                    "STRING",
                    {"multiline": False, "default": "", "tooltip": "Folder holding the assets to catalogue."},
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
                    {"multiline": False, "default": "", "tooltip": "Destination folder, for 'organise into a copy' only."},
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
                    {"default": "manifest.json", "tooltip": "Filename for the manifest, written at the library root."},
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
                "batch_size": (
                    "INT",
                    {
                        "default": 15,
                        "min": 3,
                        "max": 50,
                        "step": 1,
                        "tooltip": (
                            "Assets per Claude call. Keeps each session small enough to "
                            "finish reliably — a failed batch only costs that batch, not "
                            "the whole library, and a rerun resumes rather than restarts."
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
                        "default": 300,
                        "min": 60,
                        "max": 1800,
                        "step": 30,
                        "tooltip": "Per BATCH, not per library. Budget roughly 5s per asset in the batch.",
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

Processes **batch_size** assets per Claude call rather than the whole library at
once, and tracks progress in a hidden checkpoint file. If a run fails partway,
rerunning with the same settings resumes from where it stopped instead of
re-paying for batches already done.

Defaults to **manifest only**, which touches nothing: you get the JSON as text to
read and save yourself. Switch `write_manifest` on to have it saved into the
library, or change `mode` to let Claude reorganise and rename the files too.

Budget about 5 seconds per asset — it opens every image.
"""

    def build(
        self,
        library_path,
        mode,
        output_path,
        project_notes,
        system_prompt,
        manifest_name,
        write_manifest,
        batch_size,
        model,
        timeout_seconds,
        seed,
    ):
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

        key = checkpoint_key(mode, manifest_name, system_prompt, project_notes, assets)
        checkpoint = load_checkpoint(root, key)
        done_by_file = {}
        project = art_style = None
        if checkpoint:
            project = checkpoint.get("project")
            art_style = checkpoint.get("art_style")
            for entry in checkpoint.get("done_assets", []):
                if entry.get("file"):
                    done_by_file[entry["file"]] = entry
            print(
                f"[SF Claude Library Builder] Resuming — {len(done_by_file)}/{len(assets)} "
                f"asset(s) already catalogued from a previous run."
            )

        # Claude only ever reads images and replies with JSON; the node writes the
        # manifest itself, and the Write tool is never offered. Bash is needed
        # only to move/rename files in the organise modes.
        tools = "Read" if mode == MODE_MANIFEST else "Read,Bash"
        batches = list(chunk(assets, max(1, batch_size)))

        total_cost = 0.0
        started = time.time()

        for batch_num, batch_files in enumerate(batches, start=1):
            remaining = [f for f in batch_files if f not in done_by_file]
            if not remaining:
                continue  # fully covered by the checkpoint already

            established = (project, art_style) if project and art_style else None
            instruction = build_batch_instruction(
                mode, remaining, len(assets), project_notes, established, out_dir
            )

            command = [binary, "-p", instruction, "--output-format", "json", "--allowedTools", tools]
            if system_prompt.strip():
                command += ["--append-system-prompt", system_prompt.strip()]
            if model != "default":
                command += ["--model", model]

            print(
                f"[SF Claude Library Builder] Batch {batch_num}/{len(batches)} "
                f"({len(remaining)} asset(s))..."
            )

            def _fail(message):
                save_checkpoint(root, key, project, art_style, list(done_by_file.values()))
                raise RuntimeError(
                    f"{message} {len(done_by_file)}/{len(assets)} asset(s) are saved in a "
                    f"checkpoint — rerun with the same settings to resume rather than "
                    f"start over."
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
                _fail(
                    f"Batch {batch_num}/{len(batches)} did not finish within "
                    f"{timeout_seconds}s."
                )

            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()[:500]
                _fail(f"Batch {batch_num}/{len(batches)} failed (exit {completed.returncode}). {detail}")

            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                _fail(
                    f"Batch {batch_num}/{len(batches)}: unreadable response: "
                    f"{completed.stdout.strip()[:300]}"
                )

            if payload.get("is_error"):
                _fail(
                    f"Batch {batch_num}/{len(batches)} reported an error: "
                    f"{payload.get('result', 'unknown')}."
                )

            cost = payload.get("total_cost_usd") or 0.0
            total_cost += cost
            turns = payload.get("num_turns", "?")

            data = extract_json(payload.get("result", ""))
            if project is None:
                project = data.get("project", "Untitled project")
                art_style = data.get("art_style", "")

            expected = set(remaining)
            for entry in data.get("assets") or []:
                raw = entry.get("file")
                if not raw:
                    continue
                entry["file"] = canonicalize(raw, expected)
                done_by_file[entry["file"]] = entry

            save_checkpoint(root, key, project, art_style, list(done_by_file.values()))

            print(
                f"[SF Claude Library Builder] Batch {batch_num}/{len(batches)} done: "
                f"{turns} turns, ${cost:.2f}. Running total: "
                f"{len(done_by_file)}/{len(assets)} asset(s), ${total_cost:.2f}."
            )

        elapsed = time.time() - started

        # Assemble the final manifest in the library's original scan order.
        final_assets = [done_by_file[f] for f in assets if f in done_by_file]
        manifest_data = {
            "schema": SCHEMA_VERSION,
            "project": project or "Untitled project",
            "art_style": art_style or "",
            "generated": time.strftime("%Y-%m-%d"),
            "assets": final_assets,
        }
        manifest_text = json.dumps(manifest_data, indent=2)

        manifest_root = out_dir if mode == MODE_COPY else root
        manifest_path = os.path.join(manifest_root, manifest_name)
        if write_manifest:
            os.makedirs(manifest_root, exist_ok=True)
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write(manifest_text)

        clear_checkpoint(root)

        counts = {}
        for entry in final_assets:
            counts[entry.get("category", "?")] = counts.get(entry.get("category", "?"), 0) + 1

        report = "\n".join(
            [
                f"mode:        {mode}",
                f"scanned:     {len(assets)} file(s) in {root}",
                f"catalogued:  {len(final_assets)} asset(s) across {len(batches)} batch(es)",
                "categories:  " + (", ".join(f"{k} x{v}" for k, v in sorted(counts.items())) or "none"),
                f"art style:   {manifest_data['art_style'] or '(not set)'}",
                "manifest:    " + (manifest_path if write_manifest else "returned as text, not saved"),
                f"took:        {elapsed:.0f}s, ${total_cost:.2f} total",
            ]
        )
        print(
            f"[SF Claude Library Builder] Done: {len(final_assets)}/{len(assets)} asset(s), "
            f"{elapsed:.0f}s, ${total_cost:.2f}."
        )

        if len(final_assets) < len(assets):
            report += f"\nWARNING:     {len(assets) - len(final_assets)} file(s) were not catalogued."

        return (manifest_text, report)


NODE_CLASS_MAPPINGS = {"SFClaudeLibraryBuilder": SFClaudeLibraryBuilder}
NODE_DISPLAY_NAME_MAPPINGS = {"SFClaudeLibraryBuilder": "SF Claude Library Builder"}
