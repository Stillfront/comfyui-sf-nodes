# ABOUTME: Shared async helpers for nodes that call WaveSpeed's v3 prediction API directly
# ABOUTME: Lets those nodes run in parallel in ComfyUI: every blocking call runs off the event loop

import asyncio
import io

import numpy as np
import requests
import torch
from PIL import Image

from .utils import tensor2images

RESULT_PATH = "/api/v3/predictions/{id}/result"
TERMINAL_FAILURES = {"failed", "cancelled", "timeout", "deleted"}

# The partner image nodes downscale references to this many pixels before upload.
MAX_UPLOAD_PIXELS = 2048 * 2048

# ComfyUI runs an `async def` node as a background task and moves on to other
# ready nodes while it waits, which is how partner nodes overlap. That only
# helps if the coroutine actually yields: WaveSpeedClient uses blocking
# `requests`, so every call below goes through asyncio.to_thread.


def check_interrupted():
    """Raise if the user pressed Cancel in ComfyUI; a no-op outside ComfyUI."""
    try:
        import comfy.model_management as mm
    except ImportError:
        return
    mm.throw_exception_if_processing_interrupted()


async def call(client, fn, *args):
    """Run a blocking API call in a worker thread, turning a 401 into an error
    that says which key was used."""
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            source = client.get("source", "the SF WaveSpeed Client node")
            raise RuntimeError(
                f"WaveSpeed rejected the API key, which came from {source}. "
                f"Check it on wavespeed.ai under API Keys, or clear the api_key field "
                f"on SF WaveSpeed Client to fall back to a key saved elsewhere."
            ) from e
        raise


async def wait_for_result(api, task_id, timeout_seconds, label, interval=2):
    """Poll a prediction until it completes, yielding between polls. Returns the result."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    while True:
        check_interrupted()
        result = await asyncio.to_thread(api.get, RESULT_PATH.format(id=task_id))
        status = result.get("status")
        if status == "completed":
            return result
        if status in TERMINAL_FAILURES:
            raise RuntimeError(f"{label} task {status}: {result.get('error') or result}")
        if loop.time() - started > timeout_seconds:
            raise RuntimeError(f"{label} task {task_id} still '{status}' after {timeout_seconds}s.")
        await asyncio.sleep(interval)


async def submit_and_collect(api, client, endpoint, payload, count, timeout_seconds, label):
    """Submit `count` identical predictions at once and wait for all of them.
    Returns every output URL, in submission order."""

    async def one():
        task = await call(client, api.post, endpoint, payload)
        if not task.get("id"):
            raise RuntimeError(f"WaveSpeed did not return a task id: {task}")
        result = await wait_for_result(api, task["id"], timeout_seconds, label)
        outputs = result.get("outputs") or []
        return outputs if isinstance(outputs, list) else [outputs]

    batches = await asyncio.gather(*(one() for _ in range(count)))
    return [url for batch in batches for url in batch]


def flatten_images(tensors):
    """Every frame of every IMAGE tensor, as PIL images."""
    frames = []
    for tensor in tensors:
        if tensor is None:
            continue
        batch = tensor if tensor.dim() == 4 else tensor.unsqueeze(0)
        frames.extend(tensor2images(batch))
    return frames


def downscale(image, max_pixels=MAX_UPLOAD_PIXELS):
    w, h = image.size
    if w * h <= max_pixels:
        return image
    scale = (max_pixels / (w * h)) ** 0.5
    return image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


async def upload_images(api, client, images):
    """Upload references concurrently, downscaled first. Returns their URLs in order."""
    return list(await asyncio.gather(*(call(client, api.upload_file, downscale(img)) for img in images)))


async def fetch_images(urls, timeout=120):
    """Download output images concurrently."""

    def get(url):
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content))

    return list(await asyncio.gather(*(asyncio.to_thread(get, url) for url in urls)))


def _has_alpha(image):
    return image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)


def to_image_batch(frames):
    """One IMAGE tensor from PIL frames. Keeps alpha when any frame is transparent;
    resizes stragglers to the first frame, since a batch must share one size."""
    if not frames:
        raise RuntimeError("WaveSpeed returned no images.")
    mode = "RGBA" if any(_has_alpha(f) for f in frames) else "RGB"
    width, height = frames[0].size
    tensors = []
    for frame in frames:
        if frame.size != (width, height):
            frame = frame.resize((width, height), Image.LANCZOS)
        tensors.append(torch.from_numpy(np.asarray(frame.convert(mode), dtype=np.float32) / 255.0)[None,])
    return torch.cat(tensors, dim=0)
