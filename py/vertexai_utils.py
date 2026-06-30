# ABOUTME: Vertex AI utility functions for image conversion and processing
# ABOUTME: Shared utilities for all Vertex AI nodes (Imagen, Gemini, Veo, etc.)

import base64
import io
import os
import tempfile

import numpy as np
import torch
from PIL import Image


def tensor_to_pil(tensor):
    """
    Converts a torch.Tensor to a PIL Image.

    Args:
        tensor (torch.Tensor): The input tensor, expected to be in a format
                               compatible with image representation.

    Returns:
        PIL.Image or None: The converted PIL Image, or None if the input is None.
    """
    if tensor is None:
        return None
    # Squeeze the tensor to remove single-dimensional entries from the shape.
    image_np = tensor.squeeze().cpu().numpy()
    # Normalize and convert to uint8 if the data is in the [0, 1] range.
    if image_np.max() <= 1.0:
        image_np = (image_np * 255).astype(np.uint8)
    else:
        image_np = image_np.astype(np.uint8)
    return Image.fromarray(image_np)


def pil_to_base64(pil_image):
    """
    Converts a PIL Image to a base64 encoded string.

    Args:
        pil_image (PIL.Image): The input PIL Image.

    Returns:
        str or None: The base64 encoded string, or None if the input is None.
    """
    if pil_image is None:
        return None
    buffered = io.BytesIO()
    pil_image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def base64_to_tensor(base64_image):
    """
    Converts a base64 encoded image string back to a torch.Tensor.

    Args:
        base64_image (str): The base64 encoded image string.

    Returns:
        torch.Tensor: The resulting image tensor.
    """
    image_data = base64.b64decode(base64_image)
    pil_image = Image.open(io.BytesIO(image_data)).convert("RGBA")
    image_array = np.array(pil_image).astype(np.float32) / 255.0
    return torch.from_numpy(image_array)[None,]


def tensor_to_temp_image_file(tensor):
    """
    Saves a tensor as a temporary image file.

    Args:
        tensor (torch.Tensor): The input image tensor.

    Returns:
        str: The path to the temporary image file.
    """
    pil_image = tensor_to_pil(tensor)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
        pil_image.save(temp_file.name)
        return temp_file.name


def pil_image_to_tensor(pil_image):
    """
    Converts a PIL Image directly to a torch.Tensor.

    Args:
        pil_image (PIL.Image): The input PIL Image.

    Returns:
        torch.Tensor: The resulting image tensor with batch dimension.
    """
    pil_image = pil_image.convert("RGBA")
    image_array = np.array(pil_image).astype(np.float32) / 255.0
    return torch.from_numpy(image_array)[None,]


def save_video_for_preview(video_bytes, output_dir, file_path=None):
    """
    Saves video data and prepares it for preview in ComfyUI.

    Args:
        video_bytes (bytes): The video data.
        output_dir (str): The directory to save the video in if no path is given.
        file_path (str, optional): The specific file path to save the video to.

    Returns:
        dict: A dictionary containing information for the ComfyUI previewer.
    """
    if file_path:
        with open(file_path, "wb") as out_file:
            out_file.write(video_bytes)
        return {
            "filename": os.path.basename(file_path),
            "subfolder": "",
            "type": "output",
        }
    else:
        with tempfile.NamedTemporaryFile(
            suffix=".mp4", delete=False, dir=output_dir
        ) as temp_file:
            temp_file.write(video_bytes)
            return {
                "filename": os.path.basename(temp_file.name),
                "subfolder": "",
                "type": "output",
                "full_path": temp_file.name,
            }
