# ABOUTME: ByteDance Seedream 5.0 Pro and Flash through WaveSpeed, generate and edit in one node
# ABOUTME: Connecting reference images switches to edit; async, so it runs in parallel

from comfy_api.latest import IO

from .wavespeed_api.client import WaveSpeedClient
from .wavespeed_api.v3 import fetch_images, flatten_images, submit_and_collect, to_image_batch, upload_images

# Display name -> WaveSpeed slug. Text-to-image is the bare slug; edit adds /edit.
MODELS = {
    "Seedream 5.0 Pro": "bytedance/seedream-v5.0-pro",
    "Seedream 5.0 Flash": "bytedance/seedream-v5.0-flash",
}
ASPECT_RATIOS = ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9",
                 "1:2", "2:1", "1:3", "3:1", "9:21", "21:9"]
RESOLUTIONS = ["1K", "1.5K", "2K"]
MAX_REFERENCES = 10


def build_payload(model, prompt, aspect_ratio, resolution, prompt_optimization, image_urls):
    payload = {"prompt": prompt, "resolution": resolution.lower(), "output_format": "png"}
    if aspect_ratio != "auto":
        payload["aspect_ratio"] = aspect_ratio
    # Only Pro documents prompt optimisation.
    if model == "Seedream 5.0 Pro":
        payload["prompt_optimization_mode"] = prompt_optimization
    if image_urls:
        payload["images"] = image_urls
    return payload


class SFWaveSpeedSeedreamV5(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="SFWaveSpeedSeedreamV5",
            display_name="SF WaveSpeed Seedream 5.0",
            category="Stillfront/WaveSpeed",
            description=(
                "Generate or edit images with ByteDance Seedream 5.0 Pro or Flash through WaveSpeed. "
                "Connect reference images to edit; leave them empty to generate."
            ),
            inputs=[
                IO.Custom("WAVESPEED_AI_API_CLIENT").Input("client"),
                IO.String.Input("prompt", multiline=True, default="",
                                tooltip="For edits, say what should change and what should stay the same."),
                IO.Combo.Input("model", options=list(MODELS),
                               tooltip="Pro: higher quality. Flash: cheaper and faster, a flat price at any resolution."),
                IO.Int.Input("seed", default=0, min=0, max=2147483647, control_after_generate=True,
                             display_mode=IO.NumberDisplay.number,
                             tooltip="Not sent to WaveSpeed, which has no seed for these models. Change it to force a re-run."),
                IO.Combo.Input("aspect_ratio", options=ASPECT_RATIOS, default="auto",
                               tooltip="'auto' follows the first reference image when editing, or the model's default otherwise."),
                IO.Combo.Input("resolution", options=RESOLUTIONS, default="1K",
                               tooltip="Seedream tops out at 2K. On Pro, 1K and 1.5K cost the same."),
                IO.Int.Input("n", default=1, min=1, max=8, display_mode=IO.NumberDisplay.number,
                             tooltip="How many images to generate. Sent as parallel requests, each billed separately."),
                IO.Image.Input("images", optional=True,
                               tooltip=f"Optional reference image(s); connecting any switches to edit. "
                               f"Use Batch Images for several (up to {MAX_REFERENCES}); the first is the main input."),
                IO.Combo.Input("prompt_optimization", options=["standard", "fast"], default="standard", advanced=True,
                               tooltip="Pro only. 'fast' is about twice as quick but follows long prompts less closely."),
                IO.Int.Input("timeout_seconds", default=600, min=60, max=3600, step=30, advanced=True),
            ],
            outputs=[IO.Image.Output()],
        )

    @classmethod
    async def execute(cls, client, prompt, model, seed, aspect_ratio, resolution, n, images=None,
                      prompt_optimization="standard", timeout_seconds=600):
        if not prompt.strip():
            raise ValueError("The prompt box is empty — Seedream needs a text instruction, even when editing.")
        if model not in MODELS:
            raise ValueError(f"Unknown model: {model}")

        references = flatten_images([images])
        if len(references) > MAX_REFERENCES:
            raise ValueError(f"Seedream accepts at most {MAX_REFERENCES} reference images, got {len(references)}.")

        api = WaveSpeedClient(api_key=client["api_key"])
        image_urls = await upload_images(api, client, references)

        endpoint = f"/api/v3/{MODELS[model]}{'/edit' if image_urls else ''}"
        payload = build_payload(model, prompt, aspect_ratio, resolution, prompt_optimization, image_urls)
        print(f"[SF Seedream 5.0] {MODELS[model]}, "
              f"{f'editing {len(image_urls)} image(s)' if image_urls else 'text-to-image'}, {resolution}, n={n}.")

        urls = await submit_and_collect(api, client, endpoint, payload, n, timeout_seconds, f"Seedream ({model})")
        return IO.NodeOutput(to_image_batch(await fetch_images(urls)))


NODE_CLASS_MAPPINGS = {"SFWaveSpeedSeedreamV5": SFWaveSpeedSeedreamV5}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedSeedreamV5": "SF WaveSpeed Seedream 5.0"}
