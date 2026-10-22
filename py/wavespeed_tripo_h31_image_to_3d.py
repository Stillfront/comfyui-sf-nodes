# ABOUTME: Tripo H3.1 image-to-3D through the WaveSpeed API — Tripo's high-detail model
# ABOUTME: Same outputs and parallel behaviour as the P2 node, for side-by-side comparison

from .wavespeed_api.client import WaveSpeedClient
from .wavespeed_api.v3 import generate_3d_model

ENDPOINT = "/api/v3/tripo3d/h3.1/image-to-3d"

TEXTURE_LEVELS = ["standard", "detailed", "none"]
QUALITIES = ["standard", "detailed"]
FACE_MIN, FACE_MAX = 1000, 2000000


def build_payload(image_url, quad, face_limit, texture, pbr, geometry_quality,
                  texture_alignment, orientation, auto_size, model_seed, texture_seed):
    """The request body. Unused options are omitted rather than sent as null."""
    if face_limit != -1 and not FACE_MIN <= face_limit <= FACE_MAX:
        raise ValueError(
            f"face_limit must be -1 (adaptive) or between {FACE_MIN:,} and {FACE_MAX:,} — "
            f"H3.1 does not go below {FACE_MIN:,} faces. Use the P2 node for lower counts."
        )

    textured = texture != "none"
    payload = {
        "image": image_url,
        "quad": quad,
        "texture": textured,
        # PBR implies textures, so it is switched off along with them.
        "pbr": bool(pbr and textured),
        "geometry_quality": geometry_quality,
        "orientation": orientation,
        "auto_size": auto_size,
    }
    if textured:
        payload["texture_quality"] = texture
        payload["texture_alignment"] = texture_alignment
    if face_limit != -1:
        payload["face_limit"] = face_limit
    if model_seed != -1:
        payload["model_seed"] = model_seed
    if texture_seed != -1 and textured:
        payload["texture_seed"] = texture_seed
    return payload


class SFWaveSpeedTripoH31ImageTo3D:
    """
    Tripo H3.1 image-to-3D via WaveSpeed: Tripo's high-detail model, at roughly
    a fifth of P2's price. Meshes from 1,000 to 2,000,000 faces.

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
                        "max": FACE_MAX,
                        "step": 100,
                        "tooltip": f"Target face count. -1 lets Tripo choose. {FACE_MIN:,}-{FACE_MAX:,}.",
                    },
                ),
                "texture": (
                    TEXTURE_LEVELS,
                    {"default": "standard", "tooltip": "'none' gives untextured geometry."},
                ),
                "pbr": ("BOOLEAN", {"default": True, "tooltip": "PBR material maps. Ignored when texture is 'none'."}),
            },
            "optional": {
                "geometry_quality": (
                    QUALITIES,
                    {"default": "standard", "tooltip": "'detailed' gives finer geometry and may cost more."},
                ),
                "texture_alignment": (
                    ["original_image", "geometry"],
                    {
                        "default": "original_image",
                        "tooltip": "Align textures to the input image, or to the generated geometry.",
                    },
                ),
                "orientation": (
                    ["default", "align_image"],
                    {"default": "default", "tooltip": "'align_image' rotates the model to match the input image."},
                ),
                "auto_size": ("BOOLEAN", {"default": False, "tooltip": "Scale the model to real-world metres."}),
                "model_seed": (
                    "INT",
                    {"default": -1, "min": -1, "max": 2147483647, "tooltip": "-1 for random geometry."},
                ),
                "texture_seed": (
                    "INT",
                    {"default": -1, "min": -1, "max": 2147483647, "tooltip": "-1 for random texturing."},
                ),
                "timeout_seconds": ("INT", {"default": 900, "min": 60, "max": 3600, "step": 30}),
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

    # async so ComfyUI can run several of these, and other async nodes, at once.
    async def generate(self, client, image, quad, face_limit, texture, pbr,
                       geometry_quality="standard", texture_alignment="original_image",
                       orientation="default", auto_size=False,
                       model_seed=-1, texture_seed=-1, timeout_seconds=900):
        api = WaveSpeedClient(api_key=client["api_key"])
        print(f"[SF Tripo H3.1] quad={quad}, faces={face_limit}, texture={texture}, geometry={geometry_quality}.")
        return await generate_3d_model(
            api, client, image, ENDPOINT,
            lambda image_url: build_payload(
                image_url, quad, face_limit, texture, pbr, geometry_quality,
                texture_alignment, orientation, auto_size, model_seed, texture_seed,
            ),
            quad, "sf_tripo_h31", timeout_seconds, "Tripo H3.1",
        )


NODE_CLASS_MAPPINGS = {"SFWaveSpeedTripoH31ImageTo3D": SFWaveSpeedTripoH31ImageTo3D}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedTripoH31ImageTo3D": "SF WaveSpeed Tripo H3.1 Image to 3D"}
