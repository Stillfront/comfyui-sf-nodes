# In file: py/wavespeed_api/requests/runwayml_upscale_v1.py

from typing import List
from pydantic import Field
from ..utils import BaseRequest

class RunwaymlUpscaleV1(BaseRequest):
    """
    Request model for the RunwayML Upscale V1 API.
    """
    video: str = Field(..., description="The video URL to upscale.")

    def build_payload(self) -> dict:
        """Builds the request payload dictionary."""
        payload = self.model_dump(exclude_none=True)
        return self._remove_empty_fields(payload)

    def get_api_path(self) -> str:
        """Gets the API path for the request."""
        return "/api/v3/runwayml/upscale-v1"

    def field_required(self) -> List[str]:
        """Returns a list of required field names."""
        return ["video"]

    def field_order(self) -> List[str]:
        """Defines the order of fields."""
        return ["video"]