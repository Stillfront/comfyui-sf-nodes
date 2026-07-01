# SF ComfyUI Nodes

![Stillfront](assets/logo.png)

A collection of custom ComfyUI nodes developed by [Stillfront](https://www.stillfront.com). All nodes are prefixed with **SF** for easy searching in ComfyUI.

---

## Installation

### Via ComfyUI Manager (recommended)

Search for **"SF ComfyUI Nodes"** in the ComfyUI Nodes Manager and click **Install**.

### Manual

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Stillfront/comfyui-sf-nodes.git
cd comfyui-sf-nodes
pip install -r requirements.txt
```

---

## Configuration

Copy `config.ini.tmp` to `config.ini` and fill in your API keys:

```ini
[API]
wavespeed_api_key = YOUR_WAVESPEED_API_KEY
```

Alternatively, set keys via environment variables:

| Variable | Used by |
|---|---|
| `WAVESPEED_API_KEY` | All WaveSpeed nodes |
| `ANTHROPIC_API_KEY` | SF LLM Chat (Claude) |
| `GEMINI_API_KEY` | SF LLM Chat (Gemini) |
| `OPENAI_API_KEY` | SF LLM Chat (GPT) |
| Google Application Default Credentials | All VertexAI nodes |

For VertexAI nodes, authenticate via the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install):
```bash
gcloud auth application-default login
```

---

## Node Categories

### Stillfront/LLM

Chat with large language models directly inside your ComfyUI workflows, with optional image input.

| Node | Description |
|---|---|
| **SF LLM Chat** | Multi-model chat supporting Claude (Opus, Sonnet, Haiku), Gemini 3 (Pro, Flash), and OpenAI GPT-5 series. Supports image input and reports token usage. |
| **SF Text Analyzer** | Analyze and process text strings within workflows. |

---

### Stillfront/VertexAI

Generate images and videos using Google Cloud Vertex AI. Requires a Google Cloud project and Application Default Credentials.

| Node | Description |
|---|---|
| **SF VertexAI Imagen 3 Text to Image** | Generate images from text using Google Imagen 3.0. Supports multiple aspect ratios, safety settings, and up to 4 images per run. |
| **SF VertexAI Imagen 4 Text to Image** | Generate images using the latest Imagen 4.0 model. |
| **SF VertexAI Imagen 4 Upscale** | Upscale images using Imagen 4.0. |
| **SF VertexAI Nano Banana Pro** | Image generation via the Nano Banana Pro model on Vertex AI. |
| **SF VertexAI Nano Banana Pro Edit** | Edit existing images using Nano Banana Pro on Vertex AI. |
| **SF VertexAI Veo 3.1 Text to Video** | Generate videos from text prompts using Google VEO 3.1 via Vertex AI. |
| **SF VertexAI Veo 3.1 Image to Video** | Animate a still image into a video using Google VEO 3.1 via Vertex AI. |

---

### Stillfront/WaveSpeed

Image and video generation nodes powered by the [WaveSpeed AI](https://wavespeed.ai) API. All nodes require the **SF WaveSpeed Client** node to authenticate.

#### Setup
Connect an **SF WaveSpeed Client** node (enter your WaveSpeed API key) to any WaveSpeed generation node.

#### Video Generation

| Node | Description |
|---|---|
| **SF WaveSpeed VEO 3.1 Text to Video** | Google VEO 3.1 text-to-video generation. |
| **SF WaveSpeed VEO 3.1 Image to Video** | Google VEO 3.1 image-to-video animation. |
| **SF WaveSpeed VEO 3.1 Reference to Video** | VEO 3.1 video generation using a reference image. |
| **SF WaveSpeed VEO 3.1 Fast Text to Video** | Faster VEO 3.1 text-to-video variant. |
| **SF WaveSpeed VEO 3.1 Fast Image to Video** | Faster VEO 3.1 image-to-video variant. |
| **SF WaveSpeed Sora 2 Text to Video** | OpenAI Sora 2 text-to-video generation. |
| **SF WaveSpeed Sora 2 Text to Video Pro** | Sora 2 Pro — higher quality text-to-video. |
| **SF WaveSpeed Sora 2 Image to Video** | OpenAI Sora 2 image-to-video animation. |
| **SF WaveSpeed Sora 2 Image to Video Pro** | Sora 2 Pro — higher quality image-to-video. |
| **SF WaveSpeed Wan 2.5 Text to Video** | WAN 2.5 text-to-video generation. |
| **SF WaveSpeed Wan 2.5 Text to Video Fast** | WAN 2.5 faster text-to-video variant. |
| **SF WaveSpeed Wan 2.5 Image to Video** | WAN 2.5 image-to-video animation. |
| **SF WaveSpeed Wan 2.5 Image to Video Fast** | WAN 2.5 faster image-to-video variant. |
| **SF WaveSpeed Wan 2.2 Animate** | WAN 2.2 image animation. |
| **SF WaveSpeed InfiniteTalk** | Animate a portrait image with audio to create a talking-head video. |
| **SF WaveSpeed InfiniteTalk Multi** | InfiniteTalk with multiple reference inputs. |

#### Image Generation

| Node | Description |
|---|---|
| **SF WaveSpeed Nano Banana Text to Image** | Nano Banana text-to-image generation. |
| **SF WaveSpeed Nano Banana Edit** | Edit images using the Nano Banana model. |
| **SF WaveSpeed Nano Banana Pro Text to Image** | Nano Banana Pro text-to-image. |
| **SF WaveSpeed Nano Banana Pro Text to Image Multi** | Nano Banana Pro with multiple inputs. |
| **SF WaveSpeed Nano Banana Pro Text to Image Ultra** | Nano Banana Pro Ultra quality variant. |
| **SF WaveSpeed Nano Banana Pro Edit** | Edit images with Nano Banana Pro. |
| **SF WaveSpeed Nano Banana Pro Edit Multi** | Nano Banana Pro edit with multiple inputs. |
| **SF WaveSpeed Nano Banana Pro Edit Ultra** | Nano Banana Pro edit Ultra quality variant. |
| **SF WaveSpeed Qwen Text to Image** | Qwen text-to-image generation. |
| **SF WaveSpeed Qwen Edit** | Edit images using Qwen. |
| **SF WaveSpeed Qwen Edit Plus** | Qwen Edit with extended capabilities. |
| **SF WaveSpeed Qwen Edit LoRA** | Qwen edit with LoRA support. |
| **SF WaveSpeed Qwen Edit Plus LoRA** | Qwen Edit Plus with LoRA support. |
| **SF WaveSpeed Seedream V4** | ByteDance Seedream V4 image generation. |
| **SF WaveSpeed Seedream V4 Sequential** | Seedream V4 sequential generation. |
| **SF WaveSpeed Seedream V4 Edit** | Edit images with Seedream V4. |
| **SF WaveSpeed Seedream V4 Edit Sequential** | Seedream V4 sequential editing. |
| **SF WaveSpeed Wan 2.5 Text to Image** | WAN 2.5 text-to-image generation. |
| **SF WaveSpeed Wan 2.5 Image Edit** | Edit images using WAN 2.5. |
| **SF WaveSpeed Flux Kontext Dev** | Flux Kontext Dev image generation. |
| **SF WaveSpeed Flux Kontext Pro** | Flux Kontext Pro image generation. |
| **SF WaveSpeed Flux Kontext Max** | Flux Kontext Max — highest quality variant. |
| **SF WaveSpeed Flux ControlNet Union Pro 2** | Flux image generation with ControlNet guidance. |

#### Upscalers

| Node | Description |
|---|---|
| **SF WaveSpeed Image Upscaler** | Upscale images via WaveSpeed AI. |
| **SF WaveSpeed Runway Upscale** | Upscale images using RunwayML via WaveSpeed. |

---

### Stillfront/Utils

Utility nodes for building and enhancing workflows.

| Node | Description |
|---|---|
| **SF Prompt List** | Combine 2–50 text inputs into a single comma-separated string. Add or remove inputs using the `inputcount` control. |
| **SF Qwen Resolution** | Visual resolution preset selector with aspect ratio preview. |
| **SF Text Analyzer** | Analyze text content within a workflow. |
| **SF Google Sheet Cell** | Read a single cell from a publicly shared Google Sheet. Specify the sheet tab by GID, row by number (1-indexed), and column by letter (A, B, C, ...). |
| **SF Google Sheet Range** | Read a range of cells from a publicly shared Google Sheet and join them into a single string with a configurable delimiter. Supports multi-row, multi-column ranges. |

**Google Sheet nodes require the sheet to be shared as "Anyone with the link can view."**
The sheet tab GID is found in the browser URL after `#gid=` when you have that tab open.

---

## Requirements

- Python 3.10+
- ComfyUI
- See `requirements.txt` for full Python dependency list

## License

MIT License — see [LICENSE](LICENSE) for details.
