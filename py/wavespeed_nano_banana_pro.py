# ABOUTME: Nano Banana 2.1, 2 and Pro through WaveSpeed, modelled on ComfyUI's "Nano Banana Pro (Google Gemini Image)" node
# ABOUTME: One node for generate and edit across models; async, so it runs in parallel

from comfy_api.latest import IO

from .wavespeed_api.client import WaveSpeedClient
from .wavespeed_api.v3 import fetch_images, flatten_images, submit_and_collect, to_image_batch, upload_images

# Display name -> WaveSpeed slug. The node id still says "Pro" because saved
# workflows reference it; the display name does not.
MODELS = {
    "Nano Banana 2.1": "google/nano-banana-2.1",
    "gemini-3-pro-image-preview": "google/nano-banana-pro",
    "Nano Banana 2 (Gemini 3.1 Flash Image)": "google/nano-banana-2",
}
NANO_BANANA_21 = "Nano Banana 2.1"
NANO_BANANA_PRO = "gemini-3-pro-image-preview"

ASPECT_RATIOS = ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
# Extreme ratios only Nano Banana 2.1 accepts.
WIDE_ASPECT_RATIOS = ["1:4", "4:1", "1:8", "8:1"]
# 8K exists only for Pro, through WaveSpeed's separate "ultra" endpoints.
RESOLUTIONS = ["1K", "2K", "4K", "8K"]
MAX_REFERENCES = 14


def endpoint_for(model, resolution, editing):
    mode = "edit" if editing else "text-to-image"
    if resolution == "8K":
        mode += "-ultra"
    return f"/api/v3/{MODELS[model]}/{mode}"


def validate(model, aspect_ratio, resolution, enable_web_search, enable_image_search):
    if aspect_ratio in WIDE_ASPECT_RATIOS and model != NANO_BANANA_21:
        raise ValueError(f"Aspect ratio {aspect_ratio} is only available with {NANO_BANANA_21}.")
    if resolution == "8K" and model != NANO_BANANA_PRO:
        raise ValueError(f"8K is only available with {NANO_BANANA_PRO}.")
    if (enable_web_search or enable_image_search) and model == NANO_BANANA_PRO:
        raise ValueError("Web and image search are only available with Nano Banana 2 and 2.1.")


def build_payload(prompt, aspect_ratio, resolution, image_urls, enable_web_search=False, enable_image_search=False):
    payload = {"prompt": prompt, "resolution": resolution.lower(), "output_format": "png"}
    if aspect_ratio != "auto":
        payload["aspect_ratio"] = aspect_ratio
    if image_urls:
        payload["images"] = image_urls
    # Both are paid add-ons, so they are only sent when switched on.
    if enable_web_search:
        payload["enable_web_search"] = True
    if enable_image_search:
        payload["enable_image_search"] = True
    return payload


class SFWaveSpeedNanoBananaPro(IO.ComfyNode):
    """Nano Banana via WaveSpeed, with the partner node's interface."""

    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="SFWaveSpeedNanoBananaPro",
            display_name="SF WaveSpeed Nano Banana",
            category="Stillfront/WaveSpeed",
            description=(
                "Generate or edit images with Google's Nano Banana 2.1, 2 or Pro through WaveSpeed. "
                "Connect reference images to edit; leave them empty to generate."
            ),
            # New inputs go at the end: saved workflows restore widget values by
            # position, so inserting one earlier would shift every value after it.
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
                    options=ASPECT_RATIOS + WIDE_ASPECT_RATIOS,
                    default="auto",
                    tooltip="If set to 'auto', matches your input image's aspect ratio; "
                    f"with no image, the model chooses. {', '.join(WIDE_ASPECT_RATIOS)} need {NANO_BANANA_21}.",
                ),
                IO.Combo.Input(
                    "resolution",
                    options=RESOLUTIONS,
                    tooltip=f"Target output resolution. 8K needs {NANO_BANANA_PRO}.",
                ),
                IO.Image.Input(
                    "images",
                    optional=True,
                    tooltip="Optional reference image(s). "
                    f"To include multiple images, use the Batch Images node (up to {MAX_REFERENCES}).",
                ),
                IO.Int.Input("timeout_seconds", default=600, min=60, max=3600, step=30, advanced=True),
                IO.Int.Input(
                    "n",
                    default=1,
                    min=1,
                    max=8,
                    display_mode=IO.NumberDisplay.number,
                    tooltip="How many images to generate. Sent as parallel requests, each billed separately.",
                ),
                IO.Boolean.Input(
                    "enable_web_search",
                    default=False,
                    advanced=True,
                    tooltip="Ground the image in live web results. Paid add-on; Nano Banana 2 and 2.1 only.",
                ),
                IO.Boolean.Input(
                    "enable_image_search",
                    default=False,
                    advanced=True,
                    tooltip="Ground the image in real reference photos found online. "
                    "Paid add-on; Nano Banana 2 and 2.1 only.",
                ),
            ],
            outputs=[IO.Image.Output()],
        )

    @classmethod
    async def execute(cls, client, prompt, model, seed, aspect_ratio, resolution, images=None,
                      timeout_seconds=600, n=1, enable_web_search=False, enable_image_search=False):
        if not prompt.strip():
            raise ValueError("The prompt box is empty — Nano Banana needs a text instruction, even when editing.")
        if model not in MODELS:
            raise ValueError(f"Unknown model: {model}")
        validate(model, aspect_ratio, resolution, enable_web_search, enable_image_search)

        references = flatten_images([images])
        if len(references) > MAX_REFERENCES:
            raise ValueError(f"The current maximum number of supported images is {MAX_REFERENCES}.")

        api = WaveSpeedClient(api_key=client["api_key"])
        image_urls = await upload_images(api, client, references)

        endpoint = endpoint_for(model, resolution, bool(image_urls))
        payload = build_payload(prompt, aspect_ratio, resolution, image_urls, enable_web_search, enable_image_search)
        print(f"[SF Nano Banana] {MODELS[model]}, "
              f"{f'editing {len(image_urls)} image(s)' if image_urls else 'text-to-image'}, {resolution}, n={n}.")

        urls = await submit_and_collect(api, client, endpoint, payload, n, timeout_seconds, f"Nano Banana ({model})")
        return IO.NodeOutput(to_image_batch(await fetch_images(urls)))


NODE_CLASS_MAPPINGS = {"SFWaveSpeedNanoBananaPro": SFWaveSpeedNanoBananaPro}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedNanoBananaPro": "SF WaveSpeed Nano Banana"}
