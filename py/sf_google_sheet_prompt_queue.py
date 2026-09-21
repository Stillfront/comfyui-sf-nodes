# ABOUTME: Dispatches prompts from a Google Sheet column, skipping rows already marked done
# ABOUTME: Status marks are written manually in the sheet; this node only reads

import csv
import io
import re

import requests

from .sf_google_sheet_cell import col_letter_to_index


def extract_spreadsheet_id(url: str) -> str:
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if match:
        return match.group(1)
    if re.match(r"^[a-zA-Z0-9-_]+$", url.strip()):
        return url.strip()
    raise ValueError(
        "Could not extract spreadsheet ID. Please provide a full Google Sheets URL."
    )


def fetch_rows(url: str, gid: str) -> list:
    """Reads a publicly shared sheet tab as a list of rows."""
    spreadsheet_id = extract_spreadsheet_id(url)
    gid = (gid or "0").strip() or "0"

    csv_url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        f"/gviz/tq?tqx=out:csv&gid={gid}"
    )

    try:
        response = requests.get(csv_url, timeout=15)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(
            f"Could not access Google Sheet (HTTP {response.status_code}). "
            f"Make sure it is shared as 'Anyone with the link can view'. Error: {e}"
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to fetch Google Sheet: {e}")

    return list(csv.reader(io.StringIO(response.content.decode("utf-8"))))


def scan_rows(rows, prompt_idx, status_idx, skip_first_row, max_rows=None):
    """Walks the sheet and returns (pending, total).

    `pending` is [(sheet_row_number, prompt), ...] for rows whose status cell is
    empty, capped at `max_rows` when given. `total` counts every prompt found.
    Scanning stops at the first row with an empty prompt cell.
    """
    pending = []
    total = 0
    start = 1 if skip_first_row else 0

    for offset in range(start, len(rows)):
        row = rows[offset]
        prompt = row[prompt_idx].strip() if prompt_idx < len(row) else ""
        if not prompt:
            break

        total += 1
        status = row[status_idx].strip() if status_idx < len(row) else ""
        if status:
            continue

        if max_rows is None or len(pending) < max_rows:
            pending.append((offset + 1, prompt))

    return pending, total


class SFGoogleSheetPromptQueue:
    """
    Sends unfinished prompts from a Google Sheet downstream as a batch.

    Reads prompts from one column and checks a second column for a completion
    mark. Rows with anything written in the status column are skipped, so each
    run picks up where the last one left off. Clearing a status cell in the
    browser queues that row again.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "url": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "https://docs.google.com/spreadsheets/d/.../edit",
                        "tooltip": (
                            "Full Google Sheets URL. "
                            "The sheet must be shared: Share → Anyone with the link → Viewer."
                        ),
                    },
                ),
                "sheet_gid": (
                    "STRING",
                    {
                        "default": "0",
                        "tooltip": (
                            "Sheet tab GID — the number after '#gid=' in the URL. "
                            "Use 0 for the first tab."
                        ),
                    },
                ),
                "prompt_col": (
                    "STRING",
                    {"default": "A", "tooltip": "Column holding the prompts (e.g. A)."},
                ),
                "status_col": (
                    "STRING",
                    {
                        "default": "B",
                        "tooltip": (
                            "Column you mark by hand when a prompt is finished. "
                            "Any text at all (done, x, executed) means skip that row."
                        ),
                    },
                ),
                "skip_first_row": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "Ignore row 1, which is usually a header.",
                    },
                ),
                "max_rows": (
                    "INT",
                    {
                        "default": 10,
                        "min": 1,
                        "max": 500,
                        "step": 1,
                        "tooltip": "Most prompts to send in a single run.",
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "dispatch"
    CATEGORY = "Stillfront/Utils"

    DESCRIPTION = """
Sends every unfinished prompt from a Google Sheet column downstream — the graph
runs once per prompt, up to **max_rows** prompts per run.

A row is treated as finished when its **status_col** cell contains any text at
all. Write `done` next to a prompt in the sheet and the next run skips it; clear
the cell and it gets queued again. Scanning stops at the first empty prompt cell.

The sheet is re-read fresh on every run, so edits you make in the browser are
always picked up. **Refresh sheet** is optional — it reports how many prompts
are pending without having to run the graph.
"""

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # The sheet changes outside ComfyUI, so never serve a cached result.
        return float("nan")

    def dispatch(self, url, sheet_gid, prompt_col, status_col, skip_first_row, max_rows):
        prompt_idx = col_letter_to_index(prompt_col)
        status_idx = col_letter_to_index(status_col)
        if prompt_idx == status_idx:
            raise ValueError(
                f"prompt_col and status_col are both '{prompt_col.upper()}'. They must differ."
            )

        rows = fetch_rows(url, sheet_gid)
        pending, total = scan_rows(rows, prompt_idx, status_idx, skip_first_row, max_rows)

        if not pending:
            if total == 0:
                raise ValueError(
                    f"No prompts found in column {prompt_col.upper()}. Check the column "
                    f"letter, the sheet GID, and the skip_first_row setting."
                )
            raise ValueError(
                f"Nothing left to run — all {total} prompt(s) in column "
                f"{prompt_col.upper()} are marked in column {status_col.upper()}. "
                f"Clear those cells in the sheet to queue them again."
            )

        print(
            f"[SF Google Sheet Prompt Queue] Sending {len(pending)} of {total} prompt(s), "
            f"rows {pending[0][0]}-{pending[-1][0]}."
        )
        return ([prompt for _, prompt in pending],)


NODE_CLASS_MAPPINGS = {"SFGoogleSheetPromptQueue": SFGoogleSheetPromptQueue}
NODE_DISPLAY_NAME_MAPPINGS = {"SFGoogleSheetPromptQueue": "SF Google Sheet Prompt Queue"}


# --- Server route backing the node's Refresh button ---------------------------

try:
    from aiohttp import web
    from server import PromptServer

    @PromptServer.instance.routes.post("/sf_gsheet/preview")
    async def _preview(request):
        body = await request.json()
        try:
            rows = fetch_rows(body.get("url", ""), body.get("sheet_gid", "0"))
            pending, total = scan_rows(
                rows,
                col_letter_to_index(body.get("prompt_col", "A")),
                col_letter_to_index(body.get("status_col", "B")),
                bool(body.get("skip_first_row", True)),
            )
            return web.json_response(
                {"ok": True, "total": total, "pending": len(pending)}
            )
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)})

except ImportError:
    pass
