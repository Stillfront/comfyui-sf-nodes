import csv
import io
import re
import requests


def col_letter_to_index(col_str: str) -> int:
    """Convert a column letter (A, B, C, ... Z, AA, AB, ...) to a 0-based index."""
    col_str = col_str.strip().upper()
    if not col_str or not col_str.isalpha():
        raise ValueError(f"Invalid column label '{col_str}'. Use letters like A, B, C, AA, AB, etc.")
    result = 0
    for char in col_str:
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result - 1


class SFGoogleSheetCell:
    """
    Reads a single cell from a publicly shared Google Sheet.
    Row is 1-indexed. Column uses letter notation (A, B, C, ...) matching Google Sheets.
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
                            "Use 0 for the first/default sheet. "
                            "Example: for ...#gid=1234567890 enter 1234567890."
                        ),
                    },
                ),
                "row": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "step": 1,
                        "tooltip": "Row number starting from 1 (matches the row numbers shown in Google Sheets).",
                    },
                ),
                "col": (
                    "STRING",
                    {
                        "default": "A",
                        "tooltip": "Column letter as shown in Google Sheets (A, B, C, ... Z, AA, AB, ...).",
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("cell_value",)
    FUNCTION = "get_cell"
    CATEGORY = "Stillfront/Utils"

    def get_cell(self, url: str, sheet_gid: str, row: int, col: str) -> tuple:
        spreadsheet_id = self._extract_id(url)
        gid = sheet_gid.strip() or "0"
        col_idx = col_letter_to_index(col)

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
        table = list(csv.reader(io.StringIO(content)))

        row_idx = row - 1

        if row_idx >= len(table):
            raise ValueError(f"Row {row} is out of range — the sheet has {len(table)} rows.")

        row_data = table[row_idx]
        if col_idx >= len(row_data):
            raise ValueError(
                f"Column '{col.upper()}' is out of range — row {row} has {len(row_data)} columns."
            )

        return (str(row_data[col_idx]),)

    def _extract_id(self, url: str) -> str:
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
        if match:
            return match.group(1)
        if re.match(r"^[a-zA-Z0-9-_]+$", url.strip()):
            return url.strip()
        raise ValueError(
            "Could not extract spreadsheet ID. Please provide a full Google Sheets URL."
        )


NODE_CLASS_MAPPINGS = {"SFGoogleSheetCell": SFGoogleSheetCell}
NODE_DISPLAY_NAME_MAPPINGS = {"SFGoogleSheetCell": "SF Google Sheet Cell"}
