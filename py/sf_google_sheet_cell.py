import csv
import io
import re
import requests


class SFGoogleSheetCell:
    """
    Reads a single cell from a publicly shared Google Sheet.
    Row and column are 1-indexed to match Google Sheets display numbers.
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
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "step": 1,
                        "tooltip": "Column number starting from 1 (A=1, B=2, C=3, etc.).",
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("cell_value",)
    FUNCTION = "get_cell"
    CATEGORY = "Stillfront/Utils"

    def get_cell(self, url: str, sheet_gid: str, row: int, col: int) -> tuple:
        spreadsheet_id = self._extract_id(url)
        gid = sheet_gid.strip() or "0"

        # gviz/tq endpoint correctly handles any sheet GID, unlike export?format=csv
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

        # Convert 1-indexed user input to 0-indexed Python list access
        row_idx = row - 1
        col_idx = col - 1

        if row_idx >= len(table):
            raise ValueError(
                f"Row {row} is out of range — the sheet has {len(table)} rows."
            )

        row_data = table[row_idx]
        if col_idx >= len(row_data):
            raise ValueError(
                f"Column {col} is out of range — row {row} has {len(row_data)} columns."
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
