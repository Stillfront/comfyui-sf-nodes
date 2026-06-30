from typing import Optional
from pydantic import Field
from ..utils import BaseRequest


class SeedreamV3(BaseRequest):
    """
    ByteDance Seedream-V3 text to image model
    """
    guidance_scale: Optional[float] = Field(default=2.5, description="The CFG (Classifier Free Guidance) scale is a measure of how close you want the model to stick to your prompt when looking for a related image to show you.")
    prompt: str = Field(..., description="The prompt to generate an image from.")
    seed: Optional[int] = Field(default=-1, description="\n            The same seed and the same prompt given to the same version of the model\n            will output the same image every time.\n        ")
    width: Optional[int] = Field(default=1024, description="The width of the generated image." , ge=512, le=2048)
    height: Optional[int] = Field(default=1024, description="The height of the generated image." , ge=512, le=2048)

    def build_payload(self) -> dict:
        """Builds the request payload dictionary."""
        payload = {
            "guidance_scale": self.guidance_scale,
            "prompt": self.prompt,
            "seed": self.seed,
            "size": f"{self.width}*{self.height}",
        }
        return self._remove_empty_fields(payload)

    def get_api_path(self):
        """Gets the API path. Corresponds to api_path in the JSON."""
        return "/api/v3/bytedance/seedream-v3"

    def field_required(self):
        return ["prompt"]

    def field_order(self):
        """Corresponds to x-order-properties in the JSON request_schema."""
        return ["prompt", "size", "seed", "guidance_scale"] 