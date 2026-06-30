# ABOUTME: Vertex AI Nano Banana (Gemini Image) image editing node
# ABOUTME: Edits images using text instructions with Google's Nano Banana Pro or Nano Banana models

import io

import numpy as np
import torch
from google import genai
from google.genai import types
from PIL import Image


class SFVertexAINanaBananaProEdit:
    """
    Edits images using text instructions with Google Vertex AI Nano Banana models.

    - Nano Banana Pro (gemini-3-pro-image-preview): Up to 4096px (4K), best quality, preview
    - Nano Banana Pro Flash (gemini-3.1-flash-image-preview): Up to 4096px (4K), fast, preview
    - Nano Banana (gemini-2.5-flash-image): Up to 1024px (1K), faster, stable

    Supports up to 14 input images for editing, style transfer, and combining elements.
    Set inputcount and click "Update inputs" button to add more image slots.
    """

    # Available models - friendly name (API ID)
    MODELS = [
        "Nano Banana (gemini-2.5-flash-image)",
        "Nano Banana Pro (gemini-3-pro-image-preview)",
        "Nano Banana Pro Flash (gemini-3.1-flash-image-preview)",
    ]

    # Supported aspect ratios
    ASPECT_RATIOS = [
        "1:1",
        "16:9",
        "9:16",
        "4:3",
        "3:4",
        "3:2",
        "2:3",
        "4:5",
        "5:4",
        "21:9",
    ]

    # Supported image sizes (Nano Banana Pro supports all, Nano Banana only 1K)
    IMAGE_SIZES = [
        "1K",
        "2K",
        "4K",
    ]

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
                        "default": "global",
                        "tooltip": "Google Cloud region (use 'global' for Gemini/Nano Banana models)",
                    },
                ),
                "edit_instruction": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Text instruction describing the edit to make (e.g., 'Make it look like a cartoon' or 'Change the background to a beach')",
                    },
                ),
                "model": (
                    cls.MODELS,
                    {
                        "default": "Nano Banana Pro (gemini-3-pro-image-preview)",
                        "tooltip": "Nano Banana: faster, 1K only. Nano Banana Pro: best quality, up to 4K. Nano Banana Pro Flash: fast, up to 4K.",
                    },
                ),
                "aspect_ratio": (
                    cls.ASPECT_RATIOS,
                    {
                        "default": "1:1",
                        "tooltip": "Output image aspect ratio",
                    },
                ),
                "image_size": (
                    cls.IMAGE_SIZES,
                    {
                        "default": "1K",
                        "tooltip": "Output image size. Nano Banana only supports 1K. Nano Banana Pro supports 1K/2K/4K.",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 2147483647,
                        "control_after_generate": True,
                        "tooltip": "Random seed for reproducible results (0 for random)",
                    },
                ),
                "inputcount": (
                    [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
                    {
                        "default": 4,
                        "tooltip": "Number of image input slots (click 'Update inputs' button after changing)",
                    },
                ),
                "image_1": ("IMAGE", {"tooltip": "Input image 1 (required)"}),
            },
            "optional": {
                "image_2": ("IMAGE", {"tooltip": "Input image 2"}),
                "image_3": ("IMAGE", {"tooltip": "Input image 3"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("edited_image", "text_response", "thoughts")
    FUNCTION = "edit"
    CATEGORY = "Stillfront/VertexAI"

    def _tensor_to_pil(self, tensor):
        """Convert a ComfyUI tensor to PIL Image."""
        if tensor is None:
            return None
        image_np = tensor.squeeze().cpu().numpy()
        if image_np.max() <= 1.0:
            image_np = (image_np * 255).astype(np.uint8)
        else:
            image_np = image_np.astype(np.uint8)
        return Image.fromarray(image_np)

    def _pil_to_tensor(self, pil_image):
        """Convert PIL Image to ComfyUI tensor (RGB, not RGBA)."""
        pil_image = pil_image.convert("RGB")
        image_array = np.array(pil_image).astype(np.float32) / 255.0
        return torch.from_numpy(image_array)[None,]

    def edit(
        self,
        project_id,
        location,
        edit_instruction,
        model,
        aspect_ratio,
        image_size,
        seed,
        inputcount,
        image_1,
        **kwargs,
    ):
        if not project_id:
            raise ValueError(
                "project_id is required. Provide your Google Cloud project ID."
            )

        if not edit_instruction.strip():
            raise ValueError("edit_instruction cannot be empty")

        # Collect all image inputs (image_1 is required, rest from kwargs)
        images = []
        if image_1 is not None:
            images.append(image_1)
        for i in range(2, inputcount + 1):
            img = kwargs.get(f"image_{i}")
            if img is not None:
                images.append(img)

        if not images:
            raise ValueError("At least one image input is required for editing")

        # Extract API model ID from display name
        api_model = model.split("(")[-1].rstrip(")")

        # Validate image_size for Nano Banana (only supports 1K)
        if api_model == "gemini-2.5-flash-image" and image_size != "1K":
            print(
                f"[SF VertexAI Nano Banana Pro Edit] Warning: Nano Banana (gemini-2.5-flash-image) only supports 1K. Falling back to 1K."
            )
            image_size = "1K"

        # Initialize the client
        client = genai.Client(vertexai=True, project=project_id, location=location)

        # Build contents - images first, then edit instruction
        parts = []

        # Add all provided images (up to 14)
        for img_tensor in images[:14]:
            pil_img = self._tensor_to_pil(img_tensor)
            img_byte_arr = io.BytesIO()
            pil_img.save(img_byte_arr, format="PNG")
            img_bytes = img_byte_arr.getvalue()
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))

        # Add the edit instruction
        parts.append(types.Part.from_text(text=edit_instruction))

        contents = [types.Content(role="user", parts=parts)]

        # Build image_config parameters
        # Note: image_size is only supported by Nano Banana Pro models (gemini-3-pro, gemini-3.1-flash)
        image_config_params = {"aspect_ratio": aspect_ratio}
        if "gemini-3-pro" in api_model or "gemini-3.1-flash" in api_model:
            image_config_params["image_size"] = image_size

        # Build generation configuration
        config = types.GenerateContentConfig(
            seed=seed if seed > 0 else None,
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(**image_config_params),
        )

        # Call the Gemini API
        try:
            response = client.models.generate_content(
                model=api_model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            raise RuntimeError(
                f"Nano Banana Edit API call failed ({api_model}): {str(e)}"
            )

        # Check finish reason for errors
        if response.candidates and response.candidates[0].finish_reason:
            finish_reason = response.candidates[0].finish_reason
            if finish_reason != types.FinishReason.STOP:
                raise ValueError(
                    f"Generation stopped due to: {finish_reason}. Try rephrasing your edit instruction."
                )

        # Process response - extract images
        try:
            image_data = response.candidates[0].content.parts[0].inline_data.data
            pil_image = Image.open(io.BytesIO(image_data)).convert("RGB")
            result_tensor = self._pil_to_tensor(pil_image)
            return (result_tensor, "", "")
        except (AttributeError, IndexError, TypeError) as e:
            raise ValueError(
                f"No valid images were returned by the API. Your request was likely blocked by safety filters. Error: {e}"
            )


# Node registration
NODE_CLASS_MAPPINGS = {"SFVertexAINanaBananaProEdit": SFVertexAINanaBananaProEdit}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SFVertexAINanaBananaProEdit": "SF VertexAI Nano Banana Pro Edit"
}
