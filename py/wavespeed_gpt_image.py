# ABOUTME: OpenAI GPT Image through WaveSpeed, modelled on ComfyUI's "OpenAI GPT Image 2.5" partner node
# ABOUTME: Same model picker, per-model controls and growing image slots, billed to a WaveSpeed account

import io

import numpy as np
import requests
import torch
from PIL import Image

from comfy_api.latest import IO

from .wavespeed_api.client import WaveSpeedClient
from .wavespeed_api.utils import tensor2images
from .wavespeed_api.v3 import call, wait_for_result

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

# The partner node downscales references to this many pixels before upload.
MAX_UPLOAD_PIXELS = 2048 * 2048


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


def _flatten(tensors):
    """Every frame of every connected IMAGE input, as PIL images."""
    frames = []
    for tensor in tensors:
        batch = tensor if tensor.dim() == 4 else tensor.unsqueeze(0)
        frames.extend(tensor2images(batch))
    return frames


def _downscale(image):
    w, h = image.size
    if w * h <= MAX_UPLOAD_PIXELS:
        return image
    scale = (MAX_UPLOAD_PIXELS / (w * h)) ** 0.5
    return image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def _has_alpha(image):
    return image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)


def _to_tensor(image, mode):
    return torch.from_numpy(np.asarray(image.convert(mode), dtype=np.float32) / 255.0)[None,]


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
    def execute(cls, client, prompt, model, n, seed, timeout_seconds=600):
        if not prompt.strip():
            raise ValueError("prompt is empty.")

        model_name = model["model"]
        if model_name not in MODELS:
            raise ValueError(f"Unknown model: {model_name}")

        references = _flatten([t for t in (model.get("images") or {}).values() if t is not None])
        limit = 10 if model_name == "gpt-image-1.5" else 16
        if len(references) > limit:
            raise ValueError(f"{model_name} accepts at most {limit} reference images, got {len(references)}.")

        api = WaveSpeedClient(api_key=client["api_key"])
        image_urls = [call(client, lambda img=img: api.upload_file(_downscale(img))) for img in references]

        endpoint = f"/api/v3/{MODELS[model_name]}/{'edit' if image_urls else 'text-to-image'}"
        payload = build_payload(model_name, prompt, model, image_urls)
        mode = f"editing {len(image_urls)} image(s)" if image_urls else "text-to-image"
        print(f"[SF GPT Image] {model_name}, {mode}, n={n}.")

        # WaveSpeed has no `n`, so submit n requests up front and collect them together.
        task_ids = []
        for _ in range(n):
            task = call(client, lambda: api.post(endpoint, payload))
            if not task.get("id"):
                raise RuntimeError(f"WaveSpeed did not return a task id: {task}")
            task_ids.append(task["id"])

        frames = []
        for task_id in task_ids:
            result = wait_for_result(api, task_id, timeout_seconds, f"GPT Image ({model_name})")
            outputs = result.get("outputs") or []
            for url in outputs if isinstance(outputs, list) else [outputs]:
                response = requests.get(url, timeout=120)
                response.raise_for_status()
                frames.append(Image.open(io.BytesIO(response.content)))

        if not frames:
            raise RuntimeError("WaveSpeed returned no images.")

        # Keep alpha when a transparent background was produced, as the partner
        # node does; otherwise return ordinary 3-channel images.
        mode = "RGBA" if any(_has_alpha(f) for f in frames) else "RGB"

        # A batch is one tensor, so frames must share a size; identical requests
        # should agree, but match them to the first rather than fail if not.
        width, height = frames[0].size
        tensors = [_to_tensor(f if f.size == (width, height) else f.resize((width, height), Image.LANCZOS), mode)
                   for f in frames]
        return IO.NodeOutput(torch.cat(tensors, dim=0))


NODE_CLASS_MAPPINGS = {"SFWaveSpeedGPTImage": SFWaveSpeedGPTImage}
NODE_DISPLAY_NAME_MAPPINGS = {"SFWaveSpeedGPTImage": "SF WaveSpeed GPT Image 2.5"}
