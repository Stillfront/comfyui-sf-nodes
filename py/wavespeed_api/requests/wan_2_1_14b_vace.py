from typing import Optional, Union, List, Any, Dict
from pydantic import BaseModel, Field
from ..utils import BaseRequest

class Wan2114BVace(BaseRequest):
    """
    VACE is an all-in-one model designed for video creation and editing. It encompasses various tasks, including reference-to-video generation (R2V), video-to-video editing (V2V), and masked video-to-video editing (MV2V), allowing users to compose these tasks freely. This functionality enables users to explore diverse possibilities and streamlines their workflows effectively, offering a range of capabilities, such as Move-Anything, Swap-Anything, Reference-Anything, Expand-Anything, Animate-Anything, and more.
    Corresponds to API JSON: api_info/wan-2.1-14b-vace.json
    """
    images: Optional[List[str]] = Field(default=None, description="URL of ref images to use while generating the video. Publicly accessible URLs.")
    video: Optional[str] = Field(default="", description="The video for generating the output. Publicly accessible URL.")
    #"enum": ["depth","pose","none"],
    task: Optional[str] = Field(default="depth", description="Extract control information from the provided video to guide video generation.")
    prompt: Optional[str] = Field(default="", description="Input prompt for video generation.")
    negative_prompt: Optional[str] = Field(default="", description="The negative prompt for generating the output.")
    mask_image: Optional[str] = Field(default=None, description="URL of the mask image. Publicly accessible URL.")
    first_image: Optional[str] = Field(default=None, description="URL of the starting image. Publicly accessible URL.")
    last_image: Optional[str] = Field(default=None, description="URL of the ending image. Publicly accessible URL.")
    duration: Optional[int] = Field(default=5, description="Video duration in seconds.", ge=5, le=10)
    # enum=["832*480", "480*832", "1280*720", "720*1280"]
    size: Optional[str] = Field(default="832*480", description="The size of the output.")
    num_inference_steps: Optional[int] = Field(default=30, description="The number of inference steps.", ge=1, le=40)
    guidance_scale: Optional[float] = Field(default=5.0, description="The guidance scale for generation.", ge=1.01, le=10.0)
    flow_shift: Optional[float] = Field(default=16.0, description="The shift value for the timestep schedule for flow matching.", ge=0.0, le=30.0)
    context_scale: Optional[float] = Field(default=1.0, ge=0.0, le=2.0)
    seed: Optional[int] = Field(default=-1, description="The seed for random number generation.")
    enable_safety_checker: Optional[bool] = Field(default=True, description="Whether to enable the safety checker.")

    def build_payload(self) -> dict:
        """Builds the request payload dictionary."""
        return self.model_dump(exclude_unset=True)

    def get_api_path(self):
        """Gets the API path. Corresponds to api_path in the JSON."""
        return "/api/v3/wavespeed-ai/wan-2.1-14b-vace"