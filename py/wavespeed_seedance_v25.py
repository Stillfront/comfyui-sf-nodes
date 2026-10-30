# ABOUTME: ByteDance Seedance 2.5 video through WaveSpeed: text-to-video, or image-to-video from a start (and end) frame
# ABOUTME: Returns a ComfyUI VIDEO plus its URL; async, so it runs in parallel

from comfy_api.latest import IO

from .wavespeed_api.client import WaveSpeedClient
from .wavespeed_api.utils import tensor2images
from .wavespeed_api.v3 import call, fetch_video, submit_and_wait

TEXT_TO_VIDEO = "/api/v3/bytedance/seedance-2.5/text-to-video"
IMAGE_TO_VIDEO = "/api/v3/bytedance/seedance-2.5/image-to-video"
ASPECT_RATIOS = ["16:9", "9:16", "4:3", "3:4", "1:1", "21:9"]
RESOLUTIONS = ["480p", "720p", "1080p", "4k"]


def build_payload(prompt, aspect_ratio, resolution, duration, generate_audio, image_url=None, last_image_url=None):
    payload = {"prompt": prompt, "resolution": resolution, "duration": duration, "generate_audio": generate_audio}
    if image_url:
        # Image-to-video takes its aspect ratio from the start frame.
        payload["image"] = image_url
        if last_image_url:
            payload["last_image"] = last_image_url
    else:
        payload["aspect_ratio"] = aspect_ratio
    return payload


class SFWaveSpeedSeedanceV25(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="SFWaveSpeedSeedanceV25",
            display_name="SF WaveSpeed Seedance 2.5",
            category="Stillfront/WaveSpeed",
            description=(
                "Generate video with native audio using ByteDance Seedance 2.5 through WaveSpeed. "
                "Connect a start frame for image-to-video; leave it empty for text-to-video."
            ),
            inputs=[
                IO.Custom("WAVESPEED_AI_API_CLIENT").Input("client"),
                IO.String.Input("prompt", multiline=True, default="",
                                tooltip="Scene, action, camera movement and mood."),
                IO.Combo.Input("resolution", options=RESOLUTIONS, default="720p",
                               tooltip="Billed per second: 480p $0.18, 720p $0.36, 1080p $0.90, 4k $1.80."),
                IO.Int.Input("duration", default=5, min=4, max=30, display_mode=IO.NumberDisplay.number,
                             tooltip="Length in seconds (4-30). Cost scales with it."),
                IO.Combo.Input("aspect_ratio", options=ASPECT_RATIOS, default="16:9",
                               tooltip="Text-to-video only; image-to-video follows the start frame."),
                IO.Boolean.Input("generate_audio", default=True, tooltip="Native audio synced to the video."),
                IO.Int.Input("seed", default=0, min=0, max=2147483647, control_after_generate=True,
                             display_mode=IO.NumberDisplay.number,
                             tooltip="Not sent to WaveSpeed. Change it to force a re-run."),
                IO.Image.Input("image", optional=True,
                               tooltip="Optional start frame; connecting it switches to image-to-video."),
                IO.Image.Input("last_image", optional=True,
                               tooltip="Optional end frame. Needs a start frame."),
                IO.Int.Input("timeout_seconds", default=1800, min=60, max=7200, step=60, advanced=True),
            ],
            outputs=[
                IO.Video.Output("video"),
                IO.String.Output("video_url", tooltip="WaveSpeed CDN link to the video."),
            ],
        )

    @classmethod
    async def execute(cls, client, prompt, resolution, duration, aspect_ratio, generate_audio, seed,
                      image=None, last_image=None, timeout_seconds=1800):
        if not prompt.strip():
            raise ValueError("The prompt box is empty — Seedance needs a description of the video.")
        if last_image is not None and image is None:
            raise ValueError("last_image needs a start frame connected to 'image' as well.")

        api = WaveSpeedClient(api_key=client["api_key"])
        image_url = last_image_url = None
        if image is not None:
            image_url = await call(client, api.upload_file, tensor2images(image)[0])
        if last_image is not None:
            last_image_url = await call(client, api.upload_file, tensor2images(last_image)[0])

        endpoint = IMAGE_TO_VIDEO if image_url else TEXT_TO_VIDEO
        payload = build_payload(prompt, aspect_ratio, resolution, duration, generate_audio, image_url, last_image_url)
        print(f"[SF Seedance 2.5] {'image' if image_url else 'text'}-to-video, {resolution}, {duration}s, "
              f"audio={generate_audio}.")

        _task_id, result = await submit_and_wait(api, client, endpoint, payload, timeout_seconds, "Seedance 2.5",
                                                 interval=5)
        outputs = result.get("outputs") or []
        urls = [u for u in (outputs if isinstance(outputs, list) else [outputs]) if isinstance(u, str)]
        if not urls:
            raise RuntimeError(f"Seedance returned no video: {result!r}")
        return IO.NodeOutput(await fetch_video(urls[0]), urls[0])


NODE_CLASS_MAPPINGS = {"SFWaveSpeedSeedanceV25": SFWaveSpeedSeedanceV25}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedSeedanceV25": "SF WaveSpeed Seedance 2.5"}
