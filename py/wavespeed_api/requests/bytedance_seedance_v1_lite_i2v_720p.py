from typing import Optional, Union, List, Any, Dict
from pydantic import BaseModel, Field
from ..utils import BaseRequest
from .bytedance_seedance_v1_lite_i2v_480p import BytedanceSeedanceV1LiteI2V480P

class ByteDanceSeedanceV1LiteI2V720P(BytedanceSeedanceV1LiteI2V480P):
    def get_api_path(self):
        """Gets the API path. Corresponds to api_path in the JSON."""
        return "/api/v3/wavespeed-ai/bytedance/seedance-v1-lite-i2v-720p"
 