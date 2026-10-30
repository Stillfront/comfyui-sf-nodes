# ABOUTME: Meshy 7.1 image-to-3D through WaveSpeed: topology control plus optional humanoid auto-rig and animation
# ABOUTME: Returns the model and, when rigged, the rigged/walk/run/preset GLBs; async, so it runs in parallel

import asyncio
import time

from comfy_api.latest import IO

from .wavespeed_api.client import WaveSpeedClient
from .wavespeed_api.utils import tensor2images
from .wavespeed_api.v3 import call, save_3d_model, submit_and_wait

ENDPOINT = "/api/v3/meshy/v7.1/image-to-3d"
POSE_NONE = "none"


def build_payload(image_url, model_type, topology, target_polycount, symmetry_mode, should_remesh, should_texture,
                  enable_pbr, geometry_resolution, pose_mode, texture_prompt, texture_image_url, enable_rigging,
                  rigging_height_meters, enable_animation, animation_action_id):
    if enable_animation and not enable_rigging:
        raise ValueError("enable_animation needs enable_rigging on.")
    payload = {
        "image": image_url,
        "model_type": model_type,
        "topology": topology,
        "target_polycount": target_polycount,
        "symmetry_mode": symmetry_mode,
        "should_remesh": should_remesh,
        "should_texture": should_texture,
        "enable_pbr": bool(enable_pbr and should_texture),
        "enable_rigging": enable_rigging,
        "enable_animation": enable_animation,
    }
    # Meshy ignores geometry_resolution for lowpoly and smart-topology.
    if model_type == "standard":
        payload["geometry_resolution"] = geometry_resolution
    if pose_mode != POSE_NONE:
        payload["pose_mode"] = pose_mode
    if should_texture and texture_prompt.strip():
        payload["texture_prompt"] = texture_prompt.strip()
    if should_texture and texture_image_url:
        payload["texture_image"] = texture_image_url
    if enable_rigging:
        payload["rigging_height_meters"] = rigging_height_meters
    if enable_animation:
        payload["animation_action_id"] = animation_action_id
    return payload


class SFWaveSpeedMeshyV71ImageTo3D(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="SFWaveSpeedMeshyV71ImageTo3D",
            display_name="SF WaveSpeed Meshy 7.1 Image to 3D",
            category="Stillfront/WaveSpeed",
            description=(
                "Image-to-3D with Meshy 7.1 through WaveSpeed. Smart topology or low-poly meshes, "
                "and optional auto-rigging and animation for humanoid characters."
            ),
            is_output_node=True,
            inputs=[
                IO.Custom("WAVESPEED_AI_API_CLIENT").Input("client"),
                IO.Image.Input("image", tooltip="Reference image. Only the first frame of a batch is used."),
                IO.Combo.Input("model_type", options=["standard", "lowpoly", "smart-topology"], default="standard",
                               tooltip="smart-topology: clean, artist-style edge flow. lowpoly: stylised low-poly."),
                IO.Combo.Input("topology", options=["triangle", "quad"], default="triangle"),
                IO.Int.Input("target_polycount", default=30000, min=100, max=300000, step=100,
                             tooltip="Target polygon count."),
                IO.Boolean.Input("should_texture", default=True,
                                 tooltip="Off gives an untextured mesh for $0.96 instead of $1.44."),
                IO.Boolean.Input("enable_pbr", default=True, tooltip="Metallic, roughness and normal maps."),
                IO.Combo.Input("pose_mode", options=[POSE_NONE, "a-pose", "t-pose"], default=POSE_NONE,
                               tooltip="Force a humanoid pose. Leave 'none' for props."),
                IO.Boolean.Input("enable_rigging", default=False,
                                 tooltip="Auto-rig a humanoid character (+$0.24). Also returns walk and run cycles."),
                IO.Boolean.Input("enable_animation", default=False,
                                 tooltip="Apply the animation preset below (+$0.144). Needs rigging."),
                IO.Image.Input("texture_image", optional=True, tooltip="Optional image to guide the texture."),
                IO.String.Input("texture_prompt", multiline=True, default="", advanced=True,
                                tooltip="Optional texture description, up to 600 characters."),
                IO.Combo.Input("geometry_resolution", options=["standard", "2k", "4k"], default="standard",
                               advanced=True, tooltip="Standard model type only. 2k +$0.24, 4k +$0.48."),
                IO.Combo.Input("symmetry_mode", options=["auto", "on", "off"], default="auto", advanced=True),
                IO.Boolean.Input("should_remesh", default=True, advanced=True,
                                 tooltip="Remesh for cleaner topology."),
                IO.Float.Input("rigging_height_meters", default=1.7, min=0.1, max=20.0, step=0.05, advanced=True,
                               tooltip="Approximate character height, used for rigging."),
                IO.Int.Input("animation_action_id", default=92, min=0, max=696, advanced=True,
                             tooltip="Meshy animation preset id (0-696)."),
                IO.Int.Input("seed", default=0, min=0, max=2147483647, control_after_generate=True, advanced=True,
                             tooltip="Not sent to WaveSpeed. Change it to force a re-run."),
                IO.Int.Input("timeout_seconds", default=1200, min=60, max=3600, step=30, advanced=True),
            ],
            outputs=[
                IO.File3DGLB.Output("GLB", tooltip="The generated model."),
                IO.File3DGLB.Output("rigged", tooltip="Rigged character, when rigging is on."),
                IO.File3DGLB.Output("walking", tooltip="Walk cycle, when rigging is on."),
                IO.File3DGLB.Output("running", tooltip="Run cycle, when rigging is on."),
                IO.File3DGLB.Output("animation", tooltip="The animation preset, when animation is on."),
                IO.String.Output("model_file", tooltip="Absolute path of the model in output/3d."),
                IO.String.Output("model_url", tooltip="WaveSpeed CDN link to the model."),
            ],
        )

    @classmethod
    async def execute(cls, client, image, model_type, topology, target_polycount, should_texture, enable_pbr,
                      pose_mode, enable_rigging, enable_animation, texture_image=None, texture_prompt="",
                      geometry_resolution="standard", symmetry_mode="auto", should_remesh=True,
                      rigging_height_meters=1.7, animation_action_id=92, seed=0, timeout_seconds=1200):
        if len(texture_prompt) > 600:
            raise ValueError(f"texture_prompt is {len(texture_prompt)} characters; Meshy allows 600.")

        api = WaveSpeedClient(api_key=client["api_key"])
        uploads = [call(client, api.upload_file, tensor2images(image)[0])]
        if texture_image is not None and should_texture:
            uploads.append(call(client, api.upload_file, tensor2images(texture_image)[0]))
        urls = await asyncio.gather(*uploads)

        payload = build_payload(
            urls[0], model_type, topology, target_polycount, symmetry_mode, should_remesh, should_texture,
            enable_pbr, geometry_resolution, pose_mode, texture_prompt, urls[1] if len(urls) > 1 else None,
            enable_rigging, rigging_height_meters, enable_animation, animation_action_id,
        )
        print(f"[SF Meshy 7.1] {model_type}, {topology}, {target_polycount} polys, texture={should_texture}, "
              f"rig={enable_rigging}, animation={enable_animation}.")

        started = time.time()
        task_id, result = await submit_and_wait(api, client, ENDPOINT, payload, timeout_seconds, "Meshy 7.1")
        outputs = result.get("outputs") or []
        outputs = [u for u in (outputs if isinstance(outputs, list) else [outputs]) if isinstance(u, str)]
        if not outputs:
            raise RuntimeError(f"Meshy returned no model: {result!r}")

        # Documented order: model, then rigged/walking/running with rigging, then the preset with animation.
        names = ["model", "rigged", "walking", "running", "animation"]
        saved = await asyncio.gather(*(
            save_3d_model(url, f"sf_meshy71_{task_id}_{name}") for name, url in zip(names, outputs)
        ))
        models = [glb for glb, _fbx, _path in saved] + [None] * (len(names) - len(saved))
        path = saved[0][2]
        print(f"[SF Meshy 7.1] Done in {time.time() - started:.0f}s -> {len(saved)} file(s), {path}")
        return IO.NodeOutput(*models, path, outputs[0])


NODE_CLASS_MAPPINGS = {"SFWaveSpeedMeshyV71ImageTo3D": SFWaveSpeedMeshyV71ImageTo3D}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedMeshyV71ImageTo3D": "SF WaveSpeed Meshy 7.1 Image to 3D"}
