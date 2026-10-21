# ABOUTME: Tripo P2 image-to-3D through the WaveSpeed API, billed to a WaveSpeed account
# ABOUTME: Emits GLB/FBX File3D outputs compatible with ComfyUI's Preview 3D and Save nodes

import os
import time
from urllib.parse import urlparse

import requests

from .wavespeed_api.client import WaveSpeedClient
from .wavespeed_api.utils import tensor2images

try:
    from comfy_api.latest import Types

    File3D = Types.File3D
except ImportError:  # older ComfyUI without 3D file types
    File3D = None

ENDPOINT = "/api/v3/tripo3d/p2/image-to-3d"
RESULT_PATH = "/api/v3/predictions/{id}/result"

TEXTURE_LEVELS = ["standard", "fast", "detailed", "extreme", "none"]
TEXTURE_VERSIONS = ["v3.5-20260815", "v3.0-20250812", "v2.5-20250123"]
ORIENTATION_UNSET = "unset (recommended)"
ORIENTATIONS = [ORIENTATION_UNSET, "+x", "-x", "+y", "-y"]
TERMINAL_FAILURES = {"failed", "cancelled", "timeout", "deleted"}


def build_payload(image_url, quad, face_limit, texture, pbr, texture_version,
                  delight, auto_size, export_uv, export_orientation, model_seed, texture_seed):
    """The request body. Unused options are omitted rather than sent as null,
    as WaveSpeed's documentation asks."""
    if face_limit != -1:
        ceiling = 25000 if quad else 50000
        if not 48 <= face_limit <= ceiling:
            raise ValueError(
                f"face_limit must be -1 (adaptive) or between 48 and {ceiling}"
                f"{' — quad meshes cap at 25,000' if quad else ''}."
            )
    if texture == "fast" and texture_version != "v3.5-20260815":
        raise ValueError("texture 'fast' requires texture_version v3.5-20260815.")

    textured = texture != "none"
    payload = {
        "image": image_url,
        "quad": quad,
        "texture": textured,
        # PBR implies textures, so it is switched off along with them.
        "pbr": bool(pbr and textured),
        "auto_size": auto_size,
        "export_uv": export_uv,
    }
    if textured:
        payload["texture_quality"] = texture
        payload["texture_version"] = texture_version
        payload["delight"] = delight
    if face_limit != -1:
        payload["face_limit"] = face_limit
    if export_orientation != ORIENTATION_UNSET:
        payload["export_orientation"] = export_orientation
    if model_seed != -1:
        payload["model_seed"] = model_seed
    if texture_seed != -1 and textured:
        payload["texture_seed"] = texture_seed
    return payload


def pick_model_url(outputs):
    """The model file URL out of a result's `outputs`, which may be a list or a string."""
    candidates = outputs if isinstance(outputs, list) else [outputs]
    urls = [u for u in candidates if isinstance(u, str) and u.startswith("http")]
    for url in urls:
        if urlparse(url).path.lower().endswith((".glb", ".fbx")):
            return url
    if urls:
        return urls[0]
    raise RuntimeError(f"No model URL in the result: {outputs!r}")


def check_interrupted():
    try:
        import comfy.model_management as mm
    except ImportError:
        return
    mm.throw_exception_if_processing_interrupted()


def output_dir():
    try:
        import folder_paths

        base = folder_paths.get_output_directory()
    except ImportError:
        base = os.getcwd()
    path = os.path.join(base, "3d")
    os.makedirs(path, exist_ok=True)
    return path


class SFWaveSpeedTripoP2ImageTo3D:
    """
    Tripo P2 image-to-3D via WaveSpeed — the same model as ComfyUI's partner
    node, billed to your WaveSpeed account instead of ComfyUI credits.

    Tripo returns FBX when quad topology is on and GLB when it is off, so the
    matching output is populated and the other is empty.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "client": ("WAVESPEED_AI_API_CLIENT",),
                "image": ("IMAGE", {"tooltip": "Reference image. Only the first frame of a batch is used."}),
                "quad": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "Quad topology instead of triangles. Output becomes FBX."},
                ),
                "face_limit": (
                    "INT",
                    {
                        "default": -1,
                        "min": -1,
                        "max": 50000,
                        "step": 100,
                        "tooltip": "Target face count. -1 lets Tripo choose. 48-50,000, or up to 25,000 with quad.",
                    },
                ),
                "texture": (
                    TEXTURE_LEVELS,
                    {"default": "standard", "tooltip": "'none' gives untextured geometry. Higher levels cost more."},
                ),
                "pbr": ("BOOLEAN", {"default": True, "tooltip": "PBR material maps. Ignored when texture is 'none'."}),
            },
            "optional": {
                "texture_version": (
                    TEXTURE_VERSIONS,
                    {"default": TEXTURE_VERSIONS[0], "tooltip": "'fast' texture requires v3.5."},
                ),
                "delight": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "Strip lighting baked into the source image before texturing."},
                ),
                "auto_size": ("BOOLEAN", {"default": False, "tooltip": "Scale the model to real-world metres."}),
                "export_uv": ("BOOLEAN", {"default": True, "tooltip": "Generate UVs. Off is faster and smaller."}),
                "export_orientation": (
                    ORIENTATIONS,
                    {
                        "default": ORIENTATION_UNSET,
                        "tooltip": (
                            "Forward axis. Leave unset if you will rig, retexture or convert the "
                            "model — Tripo warns those steps can silently come out mis-rotated."
                        ),
                    },
                ),
                "model_seed": (
                    "INT",
                    {"default": -1, "min": -1, "max": 2147483647, "tooltip": "-1 for random geometry."},
                ),
                "texture_seed": (
                    "INT",
                    {"default": -1, "min": -1, "max": 2147483647, "tooltip": "-1 for random texturing."},
                ),
                "timeout_seconds": (
                    "INT",
                    {"default": 900, "min": 60, "max": 3600, "step": 30},
                ),
            },
        }

    RETURN_TYPES = ("FILE_3D_GLB", "FILE_3D_FBX", "STRING", "STRING")
    RETURN_NAMES = ("GLB", "FBX", "model_file", "model_url")
    OUTPUT_TOOLTIPS = (
        "Populated when quad is off.",
        "Populated when quad is on.",
        "Absolute path of the downloaded model in ComfyUI's output/3d folder.",
        "WaveSpeed CDN link to the model.",
    )
    FUNCTION = "generate"
    CATEGORY = "Stillfront/WaveSpeed"
    OUTPUT_NODE = True

    def generate(self, client, image, quad, face_limit, texture, pbr,
                 texture_version=TEXTURE_VERSIONS[0], delight=True, auto_size=False,
                 export_uv=True, export_orientation=ORIENTATION_UNSET,
                 model_seed=-1, texture_seed=-1, timeout_seconds=900):
        api = WaveSpeedClient(api_key=client["api_key"])

        image_url = api.upload_file(tensor2images(image)[0])
        payload = build_payload(
            image_url, quad, face_limit, texture, pbr, texture_version, delight,
            auto_size, export_uv, export_orientation, model_seed, texture_seed,
        )

        task = api.post(ENDPOINT, payload)
        task_id = task.get("id")
        if not task_id:
            raise RuntimeError(f"WaveSpeed did not return a task id: {task}")
        print(f"[SF Tripo P2] Submitted {task_id} (quad={quad}, faces={face_limit}, texture={texture}).")

        started = time.time()
        while True:
            check_interrupted()
            result = api.get(RESULT_PATH.format(id=task_id))
            status = result.get("status")
            if status == "completed":
                break
            if status in TERMINAL_FAILURES:
                raise RuntimeError(f"Tripo P2 task {status}: {result.get('error') or result}")
            if time.time() - started > timeout_seconds:
                raise RuntimeError(f"Tripo P2 task {task_id} still '{status}' after {timeout_seconds}s.")
            time.sleep(3)

        url = pick_model_url(result.get("outputs"))
        ext = os.path.splitext(urlparse(url).path)[1].lower() or (".fbx" if quad else ".glb")
        path = os.path.join(output_dir(), f"sf_tripo_p2_{task_id}{ext}")

        response = requests.get(url, timeout=300)
        response.raise_for_status()
        with open(path, "wb") as f:
            f.write(response.content)

        print(f"[SF Tripo P2] Done in {time.time() - started:.0f}s -> {path}")

        glb = fbx = None
        if File3D is not None:
            model = File3D(path)
            glb = model if ext == ".glb" else None
            fbx = model if ext == ".fbx" else None
        return (glb, fbx, path, url)


NODE_CLASS_MAPPINGS = {"SFWaveSpeedTripoP2ImageTo3D": SFWaveSpeedTripoP2ImageTo3D}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedTripoP2ImageTo3D": "SF WaveSpeed Tripo P2 Image to 3D"}
