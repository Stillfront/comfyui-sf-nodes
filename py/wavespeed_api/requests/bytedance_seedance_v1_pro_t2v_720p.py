from typing import Optional, Union, List, Any, Dict
from pydantic import BaseModel, Field
from ..utils import BaseRequest

from .bytedance_seedance_v1_lite_t2v_480p import BytedanceSeedanceV1LiteT2V480P

class BytedanceSeedanceV1ProT2V720P(BytedanceSeedanceV1LiteT2V480P):
    def get_api_path(self):
        """Gets the API path. Corresponds to api_path in the JSON."""
        return "/api/v3/bytedance/seedance-v1-pro-t2v-720p"
