import csv
import io
import re
import requests

from .sf_google_sheet_cell import col_letter_to_index


class SFGoogleSheetRange:
    """
    Reads a range of cells from a publicly shared Google Sheet and joins them
    into a single string using a configurable delimiter.
    Cells are read left to right, top to bottom.
    Row numbers are 1-indexed. Columns use letter notation (A, B, C, ...) matching Google Sheets.
    The sheet must be shared as "Anyone with the link can view."
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
                            "Sheet tab GID — found in the URL after '#gid='. "
                            "Use 0 for the first/default sheet."
                        ),
                    },
                ),
                "start_row": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "step": 1,
                        "tooltip": "First row of the range (1 = first row in the sheet).",
                    },
                ),
                "start_col": (
                    "STRING",
                    {
                        "default": "A",
                        "tooltip": "First column of the range (e.g. A, B, C, AA, ...).",
                    },
                ),
                "end_row": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "step": 1,
                        "tooltip": "Last row of the range (inclusive).",
                    },
                ),
                "end_col": (
                    "STRING",
                    {
                        "default": "A",
                        "tooltip": "Last column of the range (inclusive, e.g. A, B, C, AA, ...).",
                    },
                ),
                "delimiter": (
                    "STRING",
                    {
                        "default": ", ",
                        "multiline": False,
                        "tooltip": (
                            "String placed between each cell value in the output. "
                            "Can be typed directly or connected from another string node."
                        ),
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "get_range"
    CATEGORY = "Stillfront/Utils"

    def get_range(
        self,
        url: str,
        sheet_gid: str,
        start_row: int,
        start_col: str,
        end_row: int,
        end_col: str,
        delimiter: str,
    ) -> tuple:
        start_col_idx = col_letter_to_index(start_col)
        end_col_idx = col_letter_to_index(end_col)

        if start_row > end_row:
            raise ValueError(f"start_row ({start_row}) must be ≤ end_row ({end_row}).")
        if start_col_idx > end_col_idx:
            raise ValueError(
                f"start_col '{start_col.upper()}' must be ≤ end_col '{end_col.upper()}'."
            )

        table = self._fetch_sheet(url, sheet_gid)

        cells = []
        for r in range(start_row - 1, end_row):
            if r >= len(table):
                break
            row_data = table[r]
            for c in range(start_col_idx, end_col_idx + 1):
                value = row_data[c] if c < len(row_data) else ""
                cells.append(str(value))

        return (delimiter.join(cells),)

    def _fetch_sheet(self, url: str, sheet_gid: str) -> list:
        spreadsheet_id = self._extract_id(url)
        gid = sheet_gid.strip() or "0"

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
                f"Make sure the sheet is shared as 'Anyone with the link can view'. Error: {e}"
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to fetch Google Sheet: {e}")

        content = response.content.decode("utf-8")
        return list(csv.reader(io.StringIO(content)))

    def _extract_id(self, url: str) -> str:
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
        if match:
            return match.group(1)
        if re.match(r"^[a-zA-Z0-9-_]+$", url.strip()):
            return url.strip()
        raise ValueError(
            "Could not extract spreadsheet ID. Please provide a full Google Sheets URL."
        )


NODE_CLASS_MAPPINGS = {"SFGoogleSheetRange": SFGoogleSheetRange}
NODE_DISPLAY_NAME_MAPPINGS = {"SFGoogleSheetRange": "SF Google Sheet Range"}
