# ABOUTME: Vertex AI Imagen 4.0 image upscaling node
# ABOUTME: Upscales images using Google's Imagen 4.0 upscale model (up to 17 megapixels)

import asyncio
import random

import torch
from google import genai
from google.genai import types

from .vertexai_utils import base64_to_tensor, pil_to_base64, tensor_to_temp_image_file


class SFVertexAIImagen4Upscale:
    """
    Upscales images using Google Vertex AI Imagen 4.0 upscale model.

    This node increases the resolution of images without losing detail.
    Supports upscale factors from 2x to 4x with a maximum output of 17 megapixels.
    The output aspect ratio matches the input image.
    """

    def __init__(self):
        self.client = None

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project_id": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                        "tooltip": "Google Cloud project ID",
                    },
                ),
                "location": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "us-central1",
                        "tooltip": "Google Cloud region (e.g., us-central1)",
                    },
                ),
                "image": (
                    "IMAGE",
                    {"tooltip": "Input image to upscale"},
                ),
                "upscale_factor": (
                    "FLOAT",
                    {
                        "default": 2.0,
                        "min": 1.0,
                        "max": 4.0,
                        "step": 0.1,
                        "tooltip": "Upscale factor (1.0-4.0). Max output is 17 megapixels.",
                    },
                ),
            },
            "optional": {
                "safety_filter_level": (
                    [
                        "BLOCK_ONLY_HIGH",
                        "BLOCK_MEDIUM_AND_ABOVE",
                        "BLOCK_LOW_AND_ABOVE",
                        "BLOCK_NONE",
                    ],
                    {
                        "default": "BLOCK_MEDIUM_AND_ABOVE",
                        "tooltip": "Safety filter strictness level (preview feature)",
                    },
                ),
                "person_generation": (
                    ["ALLOW_ALL", "ALLOW_ADULT", "DONT_ALLOW"],
                    {
                        "default": "ALLOW_ADULT",
                        "tooltip": "Person generation policy (preview feature)",
                    },
                ),
                "output_format": (
                    ["image/png", "image/jpeg"],
                    {"default": "image/png", "tooltip": "Output image format"},
                ),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("upscaled_image",)
    FUNCTION = "upscale"
    CATEGORY = "Stillfront/VertexAI"

    async def upscale(
        self,
        project_id,
        location,
        image,
        upscale_factor,
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="ALLOW_ADULT",
        output_format="image/png",
    ):
        if not project_id:
            raise ValueError(
                "project_id is required. Provide your Google Cloud project ID."
            )

        # Initialize the client if needed
        if self.client is None:
            self.client = genai.Client(
                vertexai=True, project=project_id, location=location
            )

        # Save input image to temp file
        image_path = tensor_to_temp_image_file(image)

        try:
            # Build configuration
            config_args = {
                "upscale_factor": upscale_factor,
                "safety_filter_level": safety_filter_level,
                "person_generation": person_generation,
                "output_mime_type": output_format,
                "include_rai_reason": True,
            }

            # Load image for API
            image_file = types.Image.from_file(location=image_path)

            # Call the Imagen Upscale API
            api_response = await asyncio.to_thread(
                self.client.models.upscale_image,
                model="imagen-4.0-upscale-preview",
                image=image_file,
                config=types.UpscaleImageConfig(**config_args),
            )

        except Exception as e:
            import os

            os.remove(image_path)
            raise RuntimeError(f"Imagen 4 Upscale API call failed: {str(e)}")

        # Clean up temp file
        import os

        os.remove(image_path)

        # Process the upscaled image
        if not api_response.generated_images:
            raise ValueError(
                "No upscaled image was returned by the API. Your request may have been blocked by safety filters."
            )

        upscaled_image = api_response.generated_images[0]
        if not upscaled_image.image.image_bytes:
            reason = getattr(upscaled_image, "rai_filtered_reason", "Unknown")
            raise ValueError(
                f"Upscaled image was blocked by safety filter. Reason: {reason}"
            )

        try:
            pil_image = upscaled_image.image._pil_image.convert("RGBA")
            result_tensor = base64_to_tensor(pil_to_base64(pil_image))
        except (ValueError, AttributeError) as e:
            raise RuntimeError(f"Failed to decode upscaled image: {e}")

        return (result_tensor,)


# Node registration
NODE_CLASS_MAPPINGS = {"SFVertexAIImagen4Upscale": SFVertexAIImagen4Upscale}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SFVertexAIImagen4Upscale": "SF VertexAI Imagen 4 Upscale"
}
