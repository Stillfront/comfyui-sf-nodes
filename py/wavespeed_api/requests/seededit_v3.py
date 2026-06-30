from typing import Optional
from pydantic import Field
from ..utils import BaseRequest


class SeedEditV3(BaseRequest):
    """
    ByteDance SeedEdit-V3 image editing model
    """
    guidance_scale: Optional[float] = Field(default=0.5, description="The guidance scale controls how much the image generation process adheres to the prompt.")
    image: str = Field(..., description="The source image URL to edit.")
    prompt: str = Field(..., description="The prompt describing desired modifications to the image.")
    seed: Optional[int] = Field(default=-1, description="\n            The same seed and the same prompt given to the same version of the model\n            will output the same image every time.\n        ")

    def build_payload(self) -> dict:
        """Builds the request payload dictionary."""
        payload = {
            "guidance_scale": self.guidance_scale,
            "image": self.image,
            "prompt": self.prompt,
            "seed": self.seed,
        }
        return self._remove_empty_fields(payload)

    def get_api_path(self):
        """Gets the API path. Corresponds to api_path in the JSON."""
        return "/api/v3/bytedance/seededit-v3"

    def field_required(self):
        return ["prompt", "image"]

    def field_order(self):
        """Corresponds to x-order-properties in the JSON request_schema."""
        return ["prompt", "image", "guidance_scale", "seed"] 