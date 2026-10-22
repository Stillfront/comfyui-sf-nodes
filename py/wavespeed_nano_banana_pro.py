# ABOUTME: Nano Banana Pro through WaveSpeed, modelled on ComfyUI's "Nano Banana Pro (Google Gemini Image)" node
# ABOUTME: Same controls and model choices as the partner node; async, so it runs in parallel

from comfy_api.latest import IO

from .wavespeed_api.client import WaveSpeedClient
from .wavespeed_api.v3 import fetch_images, flatten_images, submit_and_collect, to_image_batch, upload_images

# The partner node's model names, mapped to their WaveSpeed equivalents.
MODELS = {
    "gemini-3-pro-image-preview": "google/nano-banana-pro",
    "Nano Banana 2 (Gemini 3.1 Flash Image)": "google/nano-banana-2",
}
ASPECT_RATIOS = ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
MAX_REFERENCES = 14


def build_payload(prompt, aspect_ratio, resolution, image_urls):
    payload = {"prompt": prompt, "resolution": resolution.lower(), "output_format": "png"}
    if aspect_ratio != "auto":
        payload["aspect_ratio"] = aspect_ratio
    if image_urls:
        payload["images"] = image_urls
    return payload


class SFWaveSpeedNanoBananaPro(IO.ComfyNode):
    """Nano Banana Pro via WaveSpeed, with the partner node's interface."""

    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="SFWaveSpeedNanoBananaPro",
            display_name="SF WaveSpeed Nano Banana Pro",
            category="Stillfront/WaveSpeed",
            description="Generate or edit images with Google's Nano Banana Pro through WaveSpeed.",
            inputs=[
                IO.Custom("WAVESPEED_AI_API_CLIENT").Input("client"),
                IO.String.Input(
                    "prompt",
                    multiline=True,
                    default="",
                    tooltip="Text prompt describing the image to generate or the edits to apply. "
                    "Include any constraints, styles, or details the model should follow.",
                ),
                IO.Combo.Input("model", options=list(MODELS)),
                IO.Int.Input(
                    "seed",
                    default=42,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                    tooltip="Not sent to WaveSpeed, which has no seed for these models. "
                    "Change it to force a re-run.",
                ),
                IO.Combo.Input(
                    "aspect_ratio",
                    options=ASPECT_RATIOS,
                    default="auto",
                    tooltip="If set to 'auto', matches your input image's aspect ratio; "
                    "with no image, the model chooses.",
                ),
                IO.Combo.Input("resolution", options=["1K", "2K", "4K"], tooltip="Target output resolution."),
                IO.Image.Input(
                    "images",
                    optional=True,
                    tooltip="Optional reference image(s). "
                    f"To include multiple images, use the Batch Images node (up to {MAX_REFERENCES}).",
                ),
                IO.Int.Input("timeout_seconds", default=600, min=60, max=3600, step=30, advanced=True),
            ],
            outputs=[IO.Image.Output()],
        )

    @classmethod
    async def execute(cls, client, prompt, model, seed, aspect_ratio, resolution, images=None, timeout_seconds=600):
        if not prompt.strip():
            raise ValueError("The prompt box is empty — Nano Banana needs a text instruction, even when editing.")
        if model not in MODELS:
            raise ValueError(f"Unknown model: {model}")

        references = flatten_images([images])
        if len(references) > MAX_REFERENCES:
            raise ValueError(f"The current maximum number of supported images is {MAX_REFERENCES}.")

        api = WaveSpeedClient(api_key=client["api_key"])
        image_urls = await upload_images(api, client, references)

        endpoint = f"/api/v3/{MODELS[model]}/{'edit' if image_urls else 'text-to-image'}"
        payload = build_payload(prompt, aspect_ratio, resolution, image_urls)
        print(f"[SF Nano Banana Pro] {MODELS[model]}, "
              f"{f'editing {len(image_urls)} image(s)' if image_urls else 'text-to-image'}, {resolution}.")

        urls = await submit_and_collect(api, client, endpoint, payload, 1, timeout_seconds, "Nano Banana Pro")
        return IO.NodeOutput(to_image_batch(await fetch_images(urls)))


NODE_CLASS_MAPPINGS = {"SFWaveSpeedNanoBananaPro": SFWaveSpeedNanoBananaPro}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedNanoBananaPro": "SF WaveSpeed Nano Banana Pro"}
