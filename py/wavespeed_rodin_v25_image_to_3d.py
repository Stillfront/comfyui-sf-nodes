# ABOUTME: Hyper3D Rodin Gen-2.5 image-to-3D through WaveSpeed, with quad/triangle budgets for game assets
# ABOUTME: Same GLB/FBX/path/url outputs as the Tripo nodes; async, so it runs in parallel

import time

from comfy_api.latest import IO

from .wavespeed_api.client import WaveSpeedClient
from .wavespeed_api.v3 import (
    flatten_images,
    pick_model_url,
    save_3d_model,
    submit_and_wait,
    upload_images,
)

ENDPOINT = "/api/v3/hyper3d/rodin-v2.5/image-to-3d"

TIERS = ["Gen-2.5-Medium", "Gen-2.5-Extreme-Low", "Gen-2.5-Low", "Gen-2.5-High", "Gen-2.5-Extreme-High"]
MESHES = ["18K Quad", "4K Quad", "8K Quad", "50K Quad",
          "2K Triangle", "20K Triangle", "150K Triangle", "500K Triangle"]
MATERIALS = ["PBR", "Shaded", "All", "None"]
TEXTURE_MODE_DEFAULT = "default"
TEXTURE_MODES = [TEXTURE_MODE_DEFAULT, "legacy", "extreme-low", "low", "medium", "high"]
MAX_IMAGES = 5


def build_payload(image_urls, prompt, tier, quality_and_mesh, material, file_format, texture_delight,
                  hd_texture, ta_pose, high_pack, geometry_instruct_mode, texture_mode, use_original_alpha):
    payload = {
        "images": image_urls,
        "tier": tier,
        "quality_and_mesh": quality_and_mesh,
        "material": material,
        "geometry_file_format": file_format,
        "texture_delight": texture_delight,
        "hd_texture": hd_texture,
        "ta_pose": ta_pose,
        "geometry_instruct_mode": geometry_instruct_mode,
        "use_original_alpha": use_original_alpha,
    }
    if prompt.strip():
        payload["prompt"] = prompt
    if high_pack:
        payload["addons"] = "HighPack"
    if texture_mode != TEXTURE_MODE_DEFAULT:
        payload["texture_mode"] = texture_mode
    return payload


class SFWaveSpeedRodinV25ImageTo3D(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="SFWaveSpeedRodinV25ImageTo3D",
            display_name="SF WaveSpeed Rodin 2.5 Image to 3D",
            category="Stillfront/WaveSpeed",
            description="Image-to-3D with Hyper3D Rodin Gen-2.5 through WaveSpeed. Takes 1-5 views of one object.",
            is_output_node=True,
            inputs=[
                IO.Custom("WAVESPEED_AI_API_CLIENT").Input("client"),
                IO.Image.Input("images", tooltip=f"1-{MAX_IMAGES} views of the same object. "
                               "Use Batch Images to send several; the first is the main view."),
                IO.String.Input("prompt", multiline=True, default="",
                                tooltip="Optional. Leave empty and Rodin writes its own from the images."),
                IO.Combo.Input("quality_and_mesh", options=MESHES, default="18K Quad",
                               tooltip="Face budget and topology. Quad budgets suit game assets; "
                               "WaveSpeed's own default is 500K Triangle."),
                IO.Combo.Input("geometry_file_format", options=["fbx", "glb"], default="fbx",
                               tooltip="FBX keeps quads; GLB is always triangulated."),
                IO.Combo.Input("material", options=MATERIALS, default="PBR",
                               tooltip="PBR maps, baked Shaded colour, both (All), or geometry only (None)."),
                IO.Combo.Input("tier", options=TIERS, default="Gen-2.5-Medium",
                               tooltip="Extreme-High doubles the price; every other tier costs the same."),
                IO.Boolean.Input("texture_delight", default=True,
                                 tooltip="Remove lighting and highlights baked into the source image."),
                IO.Boolean.Input("ta_pose", default=False, tooltip="Put characters in a T- or A-pose for rigging."),
                IO.Boolean.Input("high_pack", default=False,
                                 tooltip="HighPack add-on: 4K textures and denser geometry. Adds $0.96."),
                IO.Boolean.Input("hd_texture", default=False, advanced=True,
                                 tooltip="Extra texture post-processing. No extra charge."),
                IO.Combo.Input("geometry_instruct_mode", options=["faithful", "creative"], default="faithful",
                               advanced=True, tooltip="How freely Rodin interprets the shape."),
                IO.Combo.Input("texture_mode", options=TEXTURE_MODES, default=TEXTURE_MODE_DEFAULT, advanced=True,
                               tooltip="'default' leaves it to Rodin."),
                IO.Boolean.Input("use_original_alpha", default=False, advanced=True,
                                 tooltip="Keep the input image's transparency instead of cutting out the background."),
                IO.Int.Input("seed", default=0, min=0, max=2147483647, control_after_generate=True, advanced=True,
                             tooltip="Not sent to WaveSpeed. Change it to force a re-run."),
                IO.Int.Input("timeout_seconds", default=900, min=60, max=3600, step=30, advanced=True),
            ],
            outputs=[
                IO.File3DGLB.Output("GLB", tooltip="Populated when geometry_file_format is glb."),
                IO.File3DFBX.Output("FBX", tooltip="Populated when geometry_file_format is fbx."),
                IO.String.Output("model_file", tooltip="Absolute path of the downloaded model in output/3d."),
                IO.String.Output("model_url", tooltip="WaveSpeed CDN link to the model."),
            ],
        )

    @classmethod
    async def execute(cls, client, images, prompt, quality_and_mesh, geometry_file_format, material, tier,
                      texture_delight, ta_pose, high_pack, hd_texture=False, geometry_instruct_mode="faithful",
                      texture_mode=TEXTURE_MODE_DEFAULT, use_original_alpha=False, seed=0, timeout_seconds=900):
        frames = flatten_images([images])
        if not 1 <= len(frames) <= MAX_IMAGES:
            raise ValueError(f"Rodin takes 1-{MAX_IMAGES} images, got {len(frames)}.")

        api = WaveSpeedClient(api_key=client["api_key"])
        image_urls = await upload_images(api, client, frames)
        payload = build_payload(image_urls, prompt, tier, quality_and_mesh, material, geometry_file_format,
                                texture_delight, hd_texture, ta_pose, high_pack, geometry_instruct_mode,
                                texture_mode, use_original_alpha)
        print(f"[SF Rodin 2.5] {len(image_urls)} image(s), {quality_and_mesh}, {material}, {tier}"
              f"{', HighPack' if high_pack else ''}.")

        started = time.time()
        task_id, result = await submit_and_wait(api, client, ENDPOINT, payload, timeout_seconds, "Rodin 2.5")
        url = pick_model_url(result.get("outputs"), prefer=f".{geometry_file_format}")
        glb, fbx, path = await save_3d_model(url, f"sf_rodin25_{task_id}", f".{geometry_file_format}")
        print(f"[SF Rodin 2.5] Done in {time.time() - started:.0f}s -> {path}")
        return IO.NodeOutput(glb, fbx, path, url)


NODE_CLASS_MAPPINGS = {"SFWaveSpeedRodinV25ImageTo3D": SFWaveSpeedRodinV25ImageTo3D}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedRodinV25ImageTo3D": "SF WaveSpeed Rodin 2.5 Image to 3D"}
