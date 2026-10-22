# ABOUTME: OpenAI GPT Image through WaveSpeed, modelled on ComfyUI's "OpenAI GPT Image 2.5" partner node
# ABOUTME: Same model picker, per-model controls and growing image slots; async, so it runs in parallel

from comfy_api.latest import IO

from .wavespeed_api.client import WaveSpeedClient
from .wavespeed_api.v3 import fetch_images, flatten_images, submit_and_collect, to_image_batch, upload_images

# Display name -> WaveSpeed slug. WaveSpeed does not offer gpt-image-1, so of
# the partner node's five models this carries the four that exist there.
MODELS = {
    "gpt-image-2.5-flare": "openai/gpt-image-2.5-flare",
    "gpt-image-2.5-sunburst": "openai/gpt-image-2.5-sunburst",
    "gpt-image-2": "openai/gpt-image-2",
    "gpt-image-1.5": "openai/gpt-image-1.5",
}

QUALITIES = ("low", "medium", "high")
QUALITIES_25 = ("low", "medium", "high", "xhigh", "max")
ASPECT_AUTO = "auto"
ASPECT_RATIOS = (ASPECT_AUTO, "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9",
                 "1:2", "2:1", "1:3", "3:1", "9:21", "21:9")
LEGACY_SIZES = ("auto", "1024x1024", "1024x1536", "1536x1024")


def _reference_images(max_images):
    return IO.Autogrow.Input(
        "images",
        template=IO.Autogrow.TemplateNames(
            IO.Image.Input("image"),
            names=[f"image_{i}" for i in range(1, max_images + 1)],
            min=0,
        ),
        tooltip=f"Optional reference image(s). Connecting any switches to editing. Up to {max_images}.",
    )


def _quality(qualities):
    return IO.Combo.Input(
        "quality",
        default="low",
        options=list(qualities),
        tooltip="Image quality, affects cost and generation time.",
    )


def _gpt_image_2_inputs(qualities):
    """gpt-image-2 and 2.5: WaveSpeed takes an aspect ratio plus a resolution tier
    instead of OpenAI's exact pixel sizes."""
    return [
        IO.Combo.Input(
            "aspect_ratio",
            default=ASPECT_AUTO,
            options=list(ASPECT_RATIOS),
            tooltip="'auto' follows the reference image when editing, or the model's default otherwise.",
        ),
        IO.Combo.Input("resolution", default="1k", options=["1k", "2k", "4k"], tooltip="Output resolution tier."),
        _quality(qualities),
        IO.Combo.Input("output_format", default="png", options=["png", "jpeg", "webp"]),
        _reference_images(16),
    ]


def _gpt_image_15_inputs():
    return [
        IO.Combo.Input("size", default="auto", options=list(LEGACY_SIZES), tooltip="Image size."),
        IO.Combo.Input(
            "background",
            default="auto",
            options=["auto", "opaque", "transparent"],
            tooltip="Return image with or without background. Transparent needs png output.",
        ),
        _quality(QUALITIES),
        IO.Combo.Input("output_format", default="png", options=["png", "jpeg"]),
        IO.Combo.Input(
            "input_fidelity",
            default="high",
            options=["low", "high"],
            tooltip="How closely an edit sticks to the reference images. Only used when editing.",
        ),
        _reference_images(10),
    ]


def build_payload(model_name, prompt, options, image_urls):
    """The request body for one generation. Options the user left on 'auto' are
    omitted so WaveSpeed applies its own default."""
    payload = {"prompt": prompt, "output_format": options["output_format"], "quality": options["quality"]}

    if model_name == "gpt-image-1.5":
        if options["background"] == "transparent" and options["output_format"] != "png":
            raise ValueError("A transparent background needs output_format 'png'.")
        payload["background"] = options["background"]
        if options["size"] != "auto":
            payload["size"] = options["size"].replace("x", "*")
        if image_urls:
            payload["input_fidelity"] = options["input_fidelity"]
    else:
        payload["resolution"] = options["resolution"]
        if options["aspect_ratio"] != ASPECT_AUTO:
            payload["aspect_ratio"] = options["aspect_ratio"]

    if image_urls:
        payload["images"] = image_urls
    return payload


class SFWaveSpeedGPTImage(IO.ComfyNode):
    """GPT Image via WaveSpeed. Mirrors the partner node's interface; the
    differences come from what WaveSpeed's API actually accepts."""

    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="SFWaveSpeedGPTImage",
            display_name="SF WaveSpeed GPT Image 2.5",
            category="Stillfront/WaveSpeed",
            description=(
                "Generates or edits images with OpenAI's GPT Image models through WaveSpeed. "
                "Connect reference images to edit; leave them empty to generate."
            ),
            inputs=[
                IO.Custom("WAVESPEED_AI_API_CLIENT").Input("client"),
                IO.String.Input("prompt", default="", multiline=True, tooltip="Text prompt for GPT Image"),
                IO.DynamicCombo.Input(
                    "model",
                    options=[
                        IO.DynamicCombo.Option("gpt-image-2.5-flare", _gpt_image_2_inputs(QUALITIES_25)),
                        IO.DynamicCombo.Option("gpt-image-2.5-sunburst", _gpt_image_2_inputs(QUALITIES_25)),
                        IO.DynamicCombo.Option("gpt-image-2", _gpt_image_2_inputs(QUALITIES)),
                        IO.DynamicCombo.Option("gpt-image-1.5", _gpt_image_15_inputs()),
                    ],
                ),
                IO.Int.Input(
                    "n",
                    default=1,
                    min=1,
                    max=8,
                    step=1,
                    tooltip="How many images to generate. Sent as parallel requests, each billed separately.",
                    display_mode=IO.NumberDisplay.number,
                ),
                IO.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=2147483647,
                    step=1,
                    display_mode=IO.NumberDisplay.number,
                    control_after_generate=True,
                    tooltip="Not sent to WaveSpeed, which has no seed for these models. Change it to force a re-run.",
                ),
                IO.Int.Input(
                    "timeout_seconds",
                    default=600,
                    min=60,
                    max=3600,
                    step=30,
                    advanced=True,
                ),
            ],
            outputs=[IO.Image.Output()],
        )

    @classmethod
    async def execute(cls, client, prompt, model, n, seed, timeout_seconds=600):
        if not prompt.strip():
            raise ValueError("The prompt box is empty — GPT Image needs a text instruction, even when editing.")

        model_name = model["model"]
        if model_name not in MODELS:
            raise ValueError(f"Unknown model: {model_name}")

        references = flatten_images((model.get("images") or {}).values())
        limit = 10 if model_name == "gpt-image-1.5" else 16
        if len(references) > limit:
            raise ValueError(f"{model_name} accepts at most {limit} reference images, got {len(references)}.")

        api = WaveSpeedClient(api_key=client["api_key"])
        image_urls = await upload_images(api, client, references)

        endpoint = f"/api/v3/{MODELS[model_name]}/{'edit' if image_urls else 'text-to-image'}"
        payload = build_payload(model_name, prompt, model, image_urls)
        mode = f"editing {len(image_urls)} image(s)" if image_urls else "text-to-image"
        print(f"[SF GPT Image] {model_name}, {mode}, n={n}.")

        # WaveSpeed has no `n`, so n requests are submitted together.
        urls = await submit_and_collect(api, client, endpoint, payload, n, timeout_seconds,
                                        f"GPT Image ({model_name})")
        return IO.NodeOutput(to_image_batch(await fetch_images(urls)))


NODE_CLASS_MAPPINGS = {"SFWaveSpeedGPTImage": SFWaveSpeedGPTImage}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedGPTImage": "SF WaveSpeed GPT Image 2.5"}
