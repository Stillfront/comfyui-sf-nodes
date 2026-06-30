# ABOUTME: Main entry point for ComfyUI Stillfront custom nodes
# ABOUTME: Dynamically loads all node modules from the py/ directory

import importlib.util
import os
import sys

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


def get_ext_dir(subpath=None, mkdir=False):
    """Get the extension directory path, optionally with a subpath."""
    dir = os.path.dirname(__file__)
    if subpath is not None:
        dir = os.path.join(dir, subpath)

    dir = os.path.abspath(dir)

    if mkdir and not os.path.exists(dir):
        os.makedirs(dir)
    return dir


py = get_ext_dir("py")
files = os.listdir(py)

for file in files:
    if not file.endswith(".py"):
        continue
    name = os.path.splitext(file)[0]
    try:
        imported_module = importlib.import_module(".py.{}".format(name), __name__)
        if hasattr(imported_module, "NODE_CLASS_MAPPINGS"):
            NODE_CLASS_MAPPINGS = {
                **NODE_CLASS_MAPPINGS,
                **imported_module.NODE_CLASS_MAPPINGS,
            }
        if hasattr(imported_module, "NODE_DISPLAY_NAME_MAPPINGS"):
            NODE_DISPLAY_NAME_MAPPINGS = {
                **NODE_DISPLAY_NAME_MAPPINGS,
                **imported_module.NODE_DISPLAY_NAME_MAPPINGS,
            }
    except Exception as e:
        print(f"[comfyui-stillfront] Failed to load {file}: {e}")

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
