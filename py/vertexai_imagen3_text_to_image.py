# ABOUTME: Vertex AI Imagen 3.0 text-to-image generation node
# ABOUTME: Generates images from text prompts using Google's Imagen 3.0 models

import asyncio
import os
import random

import torch
from google import genai
from google.genai import types

from .vertexai_utils import base64_to_tensor, pil_to_base64


class SFVertexAIImagen3TextToImage:
    """
    Generates images from text prompts using Google Vertex AI Imagen 3.0 models.

    Supports multiple Imagen 3.0 model variants including standard, fast, and
    capability models with configurable aspect ratios, safety settings, and
    output options.
    """

    # Resolution map: aspect_ratio -> (width, height)
    RESOLUTION_MAP = {
        "1:1": (1024, 1024),
        "16:9": (1408, 768),
        "9:16": (768, 1408),
        "4:3": (1280, 896),
        "3:4": (896, 1280),
    }

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
                        "default": os.environ.get(
                            "GOOGLE_CLOUD_LOCATION", "us-central1"
                        ),
                        "tooltip": "Google Cloud region (e.g., us-central1)",
                    },
                ),
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Text description of the image to generate",
                    },
                ),
                "model": (
                    [
                        "imagen-3.0-generate-002",
                        "imagen-3.0-generate-001",
                        "imagen-3.0-fast-generate-001",
                    ],
                    {
                        "default": "imagen-3.0-generate-002",
                        "tooltip": "Imagen 3.0 model variant",
                    },
                ),
                "aspect_ratio": (
                    list(cls.RESOLUTION_MAP.keys()),
                    {"default": "1:1", "tooltip": "Output image aspect ratio"},
                ),
                "num_images": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": 4,
                        "step": 1,
                        "tooltip": "Number of images to generate (1-4)",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": random.randint(0, 4294967295),
                        "min": 0,
                        "max": 4294967295,
                        "control_after_generate": True,
                        "tooltip": "Random seed for reproducible results",
                    },
                ),
            },
            "optional": {
                "negative_prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "What to avoid in the generated image (only supported by 001 models)",
                    },
                ),
                "safety_filter_level": (
                    [
                        "BLOCK_ONLY_HIGH",
                        "BLOCK_MEDIUM_AND_ABOVE",
                        "BLOCK_LOW_AND_ABOVE",
                        "BLOCK_NONE",
                    ],
                    {
                        "default": "BLOCK_MEDIUM_AND_ABOVE",
                        "tooltip": "Safety filter strictness level",
                    },
                ),
                "person_generation": (
                    ["ALLOW_ALL", "ALLOW_ADULT", "DONT_ALLOW"],
                    {"default": "ALLOW_ADULT", "tooltip": "Person generation policy"},
                ),
                "enhance_prompt": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Use prompt rewriter to enhance the prompt (only 002 model)",
                    },
                ),
                "output_format": (
                    ["image/png", "image/jpeg"],
                    {"default": "image/png", "tooltip": "Output image format"},
                ),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "generate"
    CATEGORY = "Stillfront/VertexAI"

    async def generate(
        self,
        project_id,
        location,
        prompt,
        model,
        aspect_ratio,
        num_images,
        seed,
        negative_prompt="",
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="ALLOW_ADULT",
        enhance_prompt=False,
        output_format="image/png",
    ):
        if not project_id:
            raise ValueError(
                "project_id is required. Set GOOGLE_CLOUD_PROJECT environment variable or provide it in the node."
            )

        if not prompt.strip():
            raise ValueError("prompt cannot be empty")

        # Initialize the client if needed
        if self.client is None:
            self.client = genai.Client(
                vertexai=True, project=project_id, location=location
            )

        # Build configuration
        config_args = {
            "aspect_ratio": aspect_ratio,
            "number_of_images": num_images,
            "seed": seed,
            "safety_filter_level": safety_filter_level,
            "person_generation": person_generation,
            "add_watermark": False,
            "output_mime_type": output_format,
            "include_rai_reason": True,
        }

        # enhance_prompt only supported by 002 model
        if model == "imagen-3.0-generate-002":
            config_args["enhance_prompt"] = enhance_prompt

        # negative_prompt only supported by 001 models
        if negative_prompt.strip() and "001" in model:
            config_args["negative_prompt"] = negative_prompt.strip()

        # Call the Imagen API
        try:
            api_response = await asyncio.to_thread(
                self.client.models.generate_images,
                model=model,
                prompt=prompt,
                config=types.GenerateImagesConfig(**config_args),
            )
        except Exception as e:
            raise RuntimeError(f"Imagen API call failed: {str(e)}")

        # Process generated images
        image_tensors = []
        for image in api_response.generated_images:
            if not image.image.image_bytes:
                reason = getattr(image, "rai_filtered_reason", "Unknown")
                print(
                    f"[SF VertexAI Imagen 3] Image blocked by safety filter. Reason: {reason}"
                )
                continue

            try:
                pil_image = image.image._pil_image.convert("RGBA")
                image_tensors.append(base64_to_tensor(pil_to_base64(pil_image)))
            except (ValueError, AttributeError) as e:
                print(
                    f"[SF VertexAI Imagen 3] Skipping image that could not be decoded: {e}"
                )
                continue

        if not image_tensors:
            raise ValueError(
                "No valid images were returned by the API. Your request was likely blocked by the safety filters."
            )

        # Stack all images into a batch tensor
        batch_tensor = torch.cat(image_tensors, 0)
        return (batch_tensor,)


# Node registration
NODE_CLASS_MAPPINGS = {"SFVertexAIImagen3TextToImage": SFVertexAIImagen3TextToImage}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SFVertexAIImagen3TextToImage": "SF VertexAI Imagen 3 Text to Image"
}
