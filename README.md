# SF ComfyUI Nodes

A collection of custom nodes for ComfyUI developed by Stillfront.

## Features

- **LLM Integration** — Chat with Claude, Gemini, and OpenAI GPT models, with optional image input
- **WaveSpeed AI** — Image and video generation (VEO, Sora, Qwen, ByteDance, Kling, VIDU, WAN, and more)
- **VertexAI** — Google Imagen3 and VEO video generation via Vertex AI
- **Utility Nodes** — Resolution presets, dynamic prompt lists, text analysis

## Installation

### Via ComfyUI Manager (recommended)

Search for **"SF ComfyUI Nodes"** in ComfyUI Manager and click Install.

### Manual

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Stillfront/comfyui-sf-nodes.git
cd comfyui-sf-nodes
pip install -r requirements.txt
```

## Configuration

1. Copy `config.ini.tmp` to `config.ini`
2. Add your API keys:
   - `WAVESPEED_API_KEY`
   - `ANTHROPIC_API_KEY` (for Claude)
   - `GEMINI_API_KEY` (for Gemini)
   - Google Cloud credentials (for VertexAI nodes)

## Node Categories

All nodes are prefixed with **SF** for easy searching in ComfyUI.

### Stillfront/LLM
- **SF LLM Chat** — Multi-model chat (Claude, Gemini, GPT) with image support and token usage reporting
- **SF Text Analyzer** — Text analysis utilities

### Stillfront/WaveSpeed
- **SF WaveSpeed Client** — API client configuration
- **SF VEO 3.1 Text to Video** — Google VEO video generation
- **SF Sora 2 Text to Video** — OpenAI Sora video generation
- **SF Qwen Image** — Qwen image generation and editing
- **SF ByteDance Seedream** — ByteDance image generation
- **SF Kling** — Kling video generation
- **SF VIDU** — VIDU video generation
- And many more...

### Stillfront/VertexAI
- **SF Imagen3** — Google Imagen3 image generation
- **SF VEO Video** — Video generation via Vertex AI

### Stillfront/Utils
- **SF Qwen Resolution** — Resolution presets with visual preview
- **SF Prompt List** — Dynamic multi-input text combiner (2–50 inputs)

## Requirements

- Python 3.10+
- ComfyUI
- See `requirements.txt` for Python dependencies

## License

MIT License
