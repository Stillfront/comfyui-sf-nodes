import configparser
import json
import os

from .wavespeed_api.client import WaveSpeedClient

PACK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOM_NODES_DIR = os.path.dirname(PACK_DIR)


def _from_ini(path):
    if not os.path.isfile(path):
        return ""
    config = configparser.ConfigParser()
    config.read(path)
    return config.get("API", "api_key", fallback="").strip()


def _from_official_pack():
    """The key saved by WaveSpeed's own ComfyUI pack, so one key serves both."""
    path = os.path.join(CUSTOM_NODES_DIR, "wavespeed-comfyui", "config.json")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            return str(json.load(f).get("api_key") or "").strip()
    except (OSError, ValueError):
        return ""


def resolve_api_key(widget_value):
    """Returns (key, where it came from). First non-empty source wins."""
    sources = [
        ("the api_key field on this node", lambda: (widget_value or "").strip()),
        ("comfyui-sf-nodes/config.ini", lambda: _from_ini(os.path.join(PACK_DIR, "config.ini"))),
        ("the WAVESPEED_API_KEY environment variable", lambda: os.environ.get("WAVESPEED_API_KEY", "").strip()),
        ("the official WaveSpeed pack's config.json", _from_official_pack),
    ]
    for label, read in sources:
        key = read()
        if key:
            return key, label
    return "", None


class SFWaveSpeedClient:
    """
    WaveSpeed AI API Client Node

    This node creates a client for connecting to the WaveSpeed AI API.
    Leave api_key empty to reuse a key saved elsewhere — see the tooltip.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "api_key": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                        "tooltip": (
                            "Leave empty (recommended) to use, in order: comfyui-sf-nodes/config.ini, "
                            "the WAVESPEED_API_KEY environment variable, or the key already saved by "
                            "WaveSpeed's official ComfyUI pack. A key typed here is saved into the "
                            "workflow file, so it travels with any workflow you share."
                        ),
                    },
                ),
            },
        }

    RETURN_TYPES = ("WAVESPEED_AI_API_CLIENT",)
    RETURN_NAMES = ("client",)

    FUNCTION = "create_client"

    CATEGORY = "Stillfront/WaveSpeed"

    def create_client(self, api_key):
        """
        Create a WaveSpeed AI API client

        Args:
            api_key: WaveSpeed AI API key; empty to look it up elsewhere

        Returns:
            dict holding the resolved key and where it came from
        """
        key, source = resolve_api_key(api_key)
        if not key:
            raise ValueError(
                "No WaveSpeed API key found. Enter one on this node, add it to "
                "comfyui-sf-nodes/config.ini, set WAVESPEED_API_KEY, or save it in "
                "WaveSpeed's official ComfyUI pack."
            )
        # Never log the key itself — only where it was found.
        print(f"[SF WaveSpeed Client] Using the API key from {source}.")
        return ({"api_key": key, "source": source},)


# Node registration
NODE_CLASS_MAPPINGS = {"SFWaveSpeedClient": SFWaveSpeedClient}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedClient": "SF WaveSpeed Client"}
