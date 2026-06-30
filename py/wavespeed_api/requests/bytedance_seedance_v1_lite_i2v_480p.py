from typing import Optional, Union, List, Any, Dict
from pydantic import BaseModel, Field
from ..utils import BaseRequest

class BytedanceSeedanceV1LiteI2V480P(BaseRequest):
    """
    ByteDance's Seedance 1.0 Lite is an optimized video generation model offering fast generation, superior prompt‑following, and quality motion realism at an affordable price.
    Corresponds to API JSON: api_info/bytedance-seedance-v1-lite-i2v-480p.json
    """
    # --- Fields based on request_schema.properties ---
    # Order from x-order-properties in JSON
    prompt: str = Field(..., description="Text prompt for video generation; Positive text prompt; Cannot exceed 2000 characters", max_length=2000)
    image: str = Field(..., description="Input image for video generation; Supported image formats include .jpg/.jpeg/.png; The image file size cannot exceed 10MB, and the image resolution should not be less than 300*300px")
    duration: Optional[int] = Field(default=5, description="Generate video duration length seconds. duration Step=5", ge=5, le=10)
    seed: Optional[int] = Field(default=-1, description="The seed for random number generation.")

    def build_payload(self) -> dict:
        """Builds the request payload dictionary."""
        return self.model_dump(exclude_unset=True)

    def get_api_path(self):
        """Gets the API path. Corresponds to api_path in the JSON."""
        return "/api/v3/bytedance/seedance-v1-lite-i2v-480p"

    def field_required(self):
        """Corresponds to request_schema.required in the JSON."""
        return ["image"]

    def field_order(self):
        """Corresponds to x-order-properties in the JSON request_schema."""
        return [
            "prompt", "image", "duration", "seed"
        ]