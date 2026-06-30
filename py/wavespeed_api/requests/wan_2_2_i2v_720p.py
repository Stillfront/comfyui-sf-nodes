# In file: py/wavespeed_api/requests/wan_2_2_i2v_720p.py

from typing import Optional, List
from pydantic import Field
from ..utils import BaseRequest

class Wan2x2I2V720p(BaseRequest):
    """
    Request model for the Wan 2.2 I2V 720p API.
    """
    image: str = Field(..., description="The image for generating the output.")
    prompt: str = Field(..., description="The prompt for generating the output.")
    negative_prompt: Optional[str] = Field("", description="The negative prompt for generating the output.")
    last_image: Optional[str] = Field("", description="The last image for generating the output.")
    duration: Optional[int] = Field(5, description="The duration of the generated media in seconds.", enum=[5, 8])
    seed: Optional[int] = Field(-1, ge=-1, le=2147483647, description="The random seed to use for the generation.")

    def build_payload(self) -> dict:
        """Builds the request payload dictionary."""
        # This uses pydantic's built-in model_dump to get all defined fields.
        # It's a more robust way than listing them manually.
        payload = self.model_dump(exclude_none=True)
        return self._remove_empty_fields(payload)

    def get_api_path(self) -> str:
        """Gets the API path for the request."""
        return "/api/v3/wavespeed-ai/wan-2.2/i2v-720p"

    def field_required(self) -> List[str]:
        """Returns a list of required field names."""
        return ["image", "prompt"]

    def field_order(self) -> List[str]:
        """Defines the order of fields."""
        return ["image", "prompt", "negative_prompt", "last_image", "duration", "seed"]