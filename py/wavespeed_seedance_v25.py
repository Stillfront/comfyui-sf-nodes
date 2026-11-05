# ABOUTME: ByteDance Seedance 2.5 video through WaveSpeed: text-to-video, image-to-video from a start (and end) frame,
# ABOUTME: or reference-to-video from numbered reference images; returns a VIDEO plus its URL, async so it runs in parallel

import re

from comfy_api.latest import IO

from .wavespeed_api.client import WaveSpeedClient
from .wavespeed_api.utils import tensor2images
from .wavespeed_api.v3 import call, fetch_video, submit_and_wait, upload_images

TEXT_TO_VIDEO = "/api/v3/bytedance/seedance-2.5/text-to-video"
IMAGE_TO_VIDEO = "/api/v3/bytedance/seedance-2.5/image-to-video"
REFERENCE_TO_VIDEO = "/api/v3/bytedance/seedance-2.5/reference-to-video"
ASPECT_RATIOS = ["16:9", "9:16", "4:3", "3:4", "1:1", "21:9"]
RESOLUTIONS = ["480p", "720p", "1080p", "4k"]
MAX_REFERENCES = 30

# "image 2", "Image 2", "image2", "@Image 2" or "<Image 2>" in the prompt.
IMAGE_MENTION = re.compile(r"(?:@\s*|<\s*)?\b[Ii]mage\s*(\d+)\b(?:\s*>)?")


def tag_references(prompt, slots):
    """Rewrites mentions of reference slots into Seedance's @Image N tags.

    `slots` are the connected slot numbers in order; they are sent in that order,
    so the tag number is the slot's position in the list. That keeps "image 3"
    pointing at slot 3 even when slot 2 is empty."""
    position = {slot: i + 1 for i, slot in enumerate(slots)}
    missing = []

    def replace(match):
        slot = int(match.group(1))
        if slot not in position:
            missing.append(slot)
            return match.group(0)
        return f"@Image {position[slot]}"

    tagged = IMAGE_MENTION.sub(replace, prompt)
    if missing:
        names = ", ".join(f"image {n}" for n in sorted(set(missing)))
        connected = ", ".join(f"image_{n}" for n in slots) or "none"
        raise ValueError(f"The prompt mentions {names}, but that reference slot is empty "
                         f"(connected: {connected}).")
    return tagged


def build_payload(prompt, aspect_ratio, resolution, duration, generate_audio, image_url=None, last_image_url=None,
                  reference_urls=None):
    payload = {"prompt": prompt, "resolution": resolution, "duration": duration, "generate_audio": generate_audio}
    if reference_urls:
        payload["reference_images"] = reference_urls
        payload["aspect_ratio"] = aspect_ratio
    elif image_url:
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
                "Connect a start frame for image-to-video, or reference images for reference-to-video "
                "(refer to them in the prompt as 'image 1', 'image 2'...); leave both empty for text-to-video."
            ),
            inputs=[
                IO.Custom("WAVESPEED_AI_API_CLIENT").Input("client"),
                IO.String.Input("prompt", multiline=True, default="",
                                tooltip="Scene, action, camera movement and mood. With references connected, "
                                "write 'image 1', 'image 2'... to mean the image in that reference slot."),
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
                IO.Image.Input("image", display_name="start_frame", optional=True,
                               tooltip="Optional start frame; connecting it switches to image-to-video."),
                IO.Image.Input("last_image", display_name="end_frame", optional=True,
                               tooltip="Optional end frame. Needs a start frame."),
                IO.Int.Input("timeout_seconds", default=1800, min=60, max=7200, step=60, advanced=True),
                # Sockets only, so appending them does not shift saved widget values.
                IO.Autogrow.Input(
                    "references",
                    template=IO.Autogrow.TemplateNames(
                        IO.Image.Input("image"), names=[f"image_{i}" for i in range(1, MAX_REFERENCES + 1)], min=0,
                    ),
                    tooltip="Reference images (characters, objects, places). Connecting any switches to "
                    "reference-to-video. The prompt's 'image 1' means slot image_1, and so on. "
                    "Only the first frame of a batch is used.",
                ),
            ],
            outputs=[
                IO.Video.Output("video"),
                IO.String.Output("video_url", tooltip="WaveSpeed CDN link to the video."),
            ],
        )

    @classmethod
    async def execute(cls, client, prompt, resolution, duration, aspect_ratio, generate_audio, seed,
                      image=None, last_image=None, timeout_seconds=1800, references=None):
        if not prompt.strip():
            raise ValueError("The prompt box is empty — Seedance needs a description of the video.")
        if last_image is not None and image is None:
            raise ValueError("end_frame needs a start_frame connected as well.")

        slots = sorted(int(name.rsplit("_", 1)[1]) for name, tensor in (references or {}).items()
                       if tensor is not None)
        if slots and (image is not None or last_image is not None):
            raise ValueError("Seedance's reference-to-video has no start or end frame. Disconnect start_frame/"
                             "end_frame, or the reference images — or add the start frame as a reference.")
        if slots:
            prompt = tag_references(prompt, slots)

        api = WaveSpeedClient(api_key=client["api_key"])
        image_url = last_image_url = None
        if image is not None:
            image_url = await call(client, api.upload_file, tensor2images(image)[0], retry=True)
        if last_image is not None:
            last_image_url = await call(client, api.upload_file, tensor2images(last_image)[0], retry=True)

        reference_urls = []
        if slots:
            frames = [tensor2images(references[f"image_{slot}"])[0] for slot in slots]
            reference_urls = await upload_images(api, client, frames)

        if reference_urls:
            endpoint, mode = REFERENCE_TO_VIDEO, f"reference-to-video ({len(reference_urls)} refs)"
        elif image_url:
            endpoint, mode = IMAGE_TO_VIDEO, "image-to-video"
        else:
            endpoint, mode = TEXT_TO_VIDEO, "text-to-video"
        payload = build_payload(prompt, aspect_ratio, resolution, duration, generate_audio, image_url, last_image_url,
                                reference_urls)
        print(f"[SF Seedance 2.5] {mode}, {resolution}, {duration}s, audio={generate_audio}.")
        if reference_urls:
            print(f"[SF Seedance 2.5] Prompt sent: {prompt}")

        _task_id, result = await submit_and_wait(api, client, endpoint, payload, timeout_seconds, "Seedance 2.5",
                                                 interval=5)
        outputs = result.get("outputs") or []
        urls = [u for u in (outputs if isinstance(outputs, list) else [outputs]) if isinstance(u, str)]
        if not urls:
            raise RuntimeError(f"Seedance returned no video: {result!r}")
        return IO.NodeOutput(await fetch_video(urls[0]), urls[0])


NODE_CLASS_MAPPINGS = {"SFWaveSpeedSeedanceV25": SFWaveSpeedSeedanceV25}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedSeedanceV25": "SF WaveSpeed Seedance 2.5"}
