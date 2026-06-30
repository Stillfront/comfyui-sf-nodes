# ABOUTME: Vertex AI Veo 3.1 text-to-video generation node
# ABOUTME: Generates videos from text prompts using Google's Veo 3.1 models

import asyncio
import os
import random

from google import genai
from google.cloud import storage
from google.genai import types

from .vertexai_utils import save_video_for_preview

try:
    import folder_paths
    from comfy.comfy_types import IO
    from comfy_api.input_impl import VideoFromFile

    HAS_COMFY_VIDEO = True
except ImportError:
    HAS_COMFY_VIDEO = False


class SFVertexAIVeo31TextToVideo:
    """
    Generates videos from text prompts using Google Vertex AI Veo 3.1 models.

    Supports text-to-video generation with configurable duration, resolution,
    aspect ratio, and audio generation. Returns video as ComfyUI VIDEO type
    or saves to GCS.
    """

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
                        "default": "us-central1",
                        "tooltip": "Google Cloud region (e.g., us-central1)",
                    },
                ),
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Text description of the video to generate",
                    },
                ),
                "model": (
                    [
                        "veo-3.1-generate-001",
                        "veo-3.1-fast-generate-001",
                        "veo-3.1-generate-preview",
                        "veo-3.1-fast-generate-preview",
                    ],
                    {
                        "default": "veo-3.1-generate-001",
                        "tooltip": "Veo 3.1 model variant (fast=quicker generation, standard=higher quality)",
                    },
                ),
                "aspect_ratio": (
                    ["16:9", "9:16"],
                    {"default": "16:9", "tooltip": "Video aspect ratio"},
                ),
                "resolution": (
                    ["1080p", "720p"],
                    {"default": "1080p", "tooltip": "Video resolution"},
                ),
                "duration_seconds": (
                    [4, 6, 8],
                    {"default": 8, "tooltip": "Video duration in seconds"},
                ),
            },
            "optional": {
                "output_gcs_uri": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": "",
                        "tooltip": "GCS URI to save output video (e.g., gs://bucket/path/). Leave empty for direct return.",
                    },
                ),
                "enhance_prompt": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "Use prompt rewriter to enhance the prompt",
                    },
                ),
                "generate_audio": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Generate audio for the video",
                    },
                ),
                "person_generation": (
                    ["allow_adult", "allow_all", "dont_allow"],
                    {"default": "allow_adult", "tooltip": "Person generation policy"},
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
        }

    if HAS_COMFY_VIDEO:
        RETURN_TYPES = (IO.VIDEO,)
    else:
        RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video",)
    FUNCTION = "generate"
    CATEGORY = "Stillfront/VertexAI"

    async def generate(
        self,
        project_id,
        location,
        prompt,
        model,
        aspect_ratio,
        resolution,
        duration_seconds,
        output_gcs_uri="",
        enhance_prompt=True,
        generate_audio=False,
        person_generation="allow_adult",
        seed=0,
    ):
        if not project_id:
            raise ValueError(
                "project_id is required. Provide your Google Cloud project ID."
            )

        if not prompt.strip():
            raise ValueError("prompt cannot be empty")

        # Initialize the client if needed
        if self.client is None:
            self.client = genai.Client(
                vertexai=True, project=project_id, location=location
            )

        # Build configuration
        config = {
            "number_of_videos": 1,
            "duration_seconds": duration_seconds,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "person_generation": person_generation,
            "enhance_prompt": enhance_prompt,
            "generate_audio": generate_audio,
            "seed": seed,
        }

        if output_gcs_uri and output_gcs_uri.strip():
            config["output_gcs_uri"] = output_gcs_uri.strip()

        config = types.GenerateVideosConfig(**config)

        # Call the Veo API
        try:
            operation = await asyncio.to_thread(
                self.client.models.generate_videos,
                model=model,
                prompt=prompt,
                config=config,
            )
        except Exception as e:
            raise RuntimeError(f"Veo 3.1 API call failed: {str(e)}")

        # Poll the operation until it is complete
        while not operation.done:
            await asyncio.sleep(8)
            operation = await asyncio.to_thread(self.client.operations.get, operation)

        if operation.error:
            raise RuntimeError(
                f"Veo 3.1 generation failed: {operation.error.get('message', 'Unknown error')}"
            )

        # Process the response
        if not operation.response:
            raise RuntimeError("No response received from Veo 3.1 API")

        if output_gcs_uri and output_gcs_uri.strip():
            # Video saved to GCS - download it
            video_uri = operation.result.generated_videos[0].video.uri

            storage_client = storage.Client(project=project_id)
            bucket_name, blob_name = video_uri.replace("gs://", "").split("/", 1)
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            video_bytes = blob.download_as_bytes()

            if HAS_COMFY_VIDEO:
                video_preview = save_video_for_preview(
                    video_bytes, folder_paths.get_temp_directory()
                )
                video_object = VideoFromFile(video_preview["full_path"])
                return (video_object,)
            else:
                return (video_uri,)
        else:
            # Video returned directly as bytes
            if not operation.result.generated_videos:
                raise RuntimeError("No video was generated")

            video = operation.result.generated_videos[0]
            video_bytes = video.video.video_bytes

            if not video_bytes:
                raise RuntimeError("No video bytes received from API")

            if HAS_COMFY_VIDEO:
                video_preview = save_video_for_preview(
                    video_bytes, folder_paths.get_temp_directory()
                )
                video_object = VideoFromFile(video_preview["full_path"])
                return (video_object,)
            else:
                # Save locally and return path
                import tempfile

                with tempfile.NamedTemporaryFile(
                    suffix=".mp4", delete=False
                ) as temp_file:
                    temp_file.write(video_bytes)
                    return (temp_file.name,)


# Node registration
NODE_CLASS_MAPPINGS = {"SFVertexAIVeo31TextToVideo": SFVertexAIVeo31TextToVideo}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SFVertexAIVeo31TextToVideo": "SF VertexAI Veo 3.1 Text to Video"
}
