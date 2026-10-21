# SF ComfyUI Nodes

![Stillfront](assets/logo.png)

**63 custom ComfyUI nodes** from [Stillfront](https://www.stillfront.com), covering AI image and
video generation, LLM integration, and tooling for working with large game asset libraries. Every
node is prefixed **SF** so they're easy to find in the node search.

| | |
|---|---|
| [**Stillfront/WaveSpeed**](#stillfrontwavespeed) | 45 nodes — image, video and 3D generation through [WaveSpeed AI](https://wavespeed.ai): VEO 3.1, Sora 2, Nano Banana, Qwen, Flux Kontext, Seedream, WAN 2.5, InfiniteTalk, Tripo P2, upscalers |
| [**Stillfront/VertexAI**](#stillfrontvertexai) | 7 nodes — Imagen 3/4, VEO 3.1 and Nano Banana Pro via Google Cloud Vertex AI |
| [**Stillfront/Utils**](#stillfrontutils) | 7 nodes — Google Sheets integration, prompt batching, resolution presets |
| [**Stillfront/LLM**](#stillfrontllm) | 4 nodes — Claude, Gemini and GPT in your graph, plus the asset library tooling below |

### Worth a look

**[The asset library workflow](#the-asset-library-workflow)** — point Claude at a folder of game
assets and it writes a searchable manifest describing every one. After that, any workflow can ask
for *"the character art that suits a boss-fight poster"* and get back the right reference images
**plus a generated prompt that already matches your project's art style** — without a single image
being opened at generation time.

Two nodes do this: **SF Claude Library Builder** catalogues once, **SF Claude Asset Director**
searches on every run. Both run on your existing Claude Code login, so there's no API key and no
per-token billing.

**[SF Google Sheet Prompt Queue](#using-sf-google-sheet-prompt-queue)** — drive a batch of
generations straight from a Google Sheet, marking rows done as you go and resuming where you left
off.

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
| **SF Claude Code** | Send text and images to Claude through the Claude Code CLI on your own machine, using your existing Claude login instead of an API key. Image slots appear as you fill them. |
| **SF Claude Asset Director** | Point Claude at an asset library and it chooses which references suit the brief and writes the image prompt to go with them. Outputs an IMAGE batch plus the prompt, ready to wire into any generation node. |
| **SF Claude Library Builder** | Point Claude at a folder of game assets and it writes a searchable manifest describing each one. Can also reorganise and rename the files. Feeds **SF Claude Asset Director**. |

#### The asset library workflow

These two nodes are a pair. **Library Builder** catalogues your assets once; **Asset Director**
then searches that catalogue on every run without ever opening an image.

```
   one time, when assets change          every generation
┌──────────────────────────────┐   ┌──────────────────────────────────┐
│ SF Claude Library Builder    │   │ SF Claude Asset Director         │
│ opens every image,           │──►│ searches the manifest,           │──► images + prompt
│ writes manifest.json         │   │ opens nothing                    │
└──────────────────────────────┘   └──────────────────────────────────┘
```

That split is the point: cataloguing is slow (~5s per asset) but happens rarely, while choosing
is instant and happens constantly.

**The manifest schema** (`sf-asset-library/1`):

```json
{
  "schema": "sf-asset-library/1",
  "project": "Fantasy RPG",
  "art_style": "Hand-painted 2D, saturated palette, thick outlines, 3/4 view",
  "generated": "2026-10-08",
  "assets": [
    {
      "file": "characters/heroes/knight_aldric.png",
      "name": "Aldric the Knight",
      "category": "character",
      "subcategory": "hero",
      "archetype": "tank",
      "tags": ["armoured", "sword", "front view", "heroic"],
      "desc": "Armoured human knight in silver plate with a red tabard, standing front-on."
    }
  ]
}
```

It's shaped for fast searching rather than for humans: one **flat list** (cheaper to scan than a
tree), the **same keys on every entry**, faceted fields (`category` / `subcategory` /
`archetype` / `tags`) to narrow by, and a one-sentence `desc` carrying the meaning. The
top-level **`art_style`** matters more than it looks — Asset Director reads it and keeps every
prompt it writes consistent with it, so a library generates in one coherent style.

**Library Builder modes:**

| Mode | What it touches |
|---|---|
| **manifest only** (default) | Nothing. Reads the images, returns the JSON as text |
| **organise into a copy** | Writes a tidy, renamed copy to `output_path`; originals untouched |
| **organise in place** | Renames and moves your actual files |

`write_manifest` is **off** by default, so the first run shows you the JSON without writing
anything. Turn it on once you're happy, or paste the text in yourself.

Start in **manifest only**. Reorganising is genuinely useful on a folder of `IMG_0021.png` and
`final_v2 copy.png`, but it moves real files — try it on a copy first.

**Large libraries are processed in batches, not one session.** `batch_size` (default 15) caps
how many assets Claude handles per call — asking it to hold a whole large library open, compose
one giant manifest, and write the file all in a single uninterrupted session is what used to
blow up in turns and cost on libraries of 100+ assets, with nothing produced at the end. Each
batch now only reads its own assets and replies with JSON; the node assembles and writes the
manifest itself, so no file-writing tool is ever handed to Claude for this.

**Reruns are incremental.** With `update_existing` on (the default), the node reads the manifest
already in the library and only catalogues files it doesn't yet describe. So the normal workflow
is: drop new assets into the folder, run the same node against the same path, and only the new
ones cost anything. Entries whose file has since been deleted are dropped automatically. Turn
`update_existing` off to re-describe everything from scratch.

*(Not available in `organise into a copy` mode, where the manifest holds post-rename paths that
can't be matched against the untouched source folder.)*

Separately, a hidden checkpoint (`.sf_library_builder_checkpoint.json`, removed automatically on
success) covers a run that dies partway. Rerunning **resumes** — finished batches are skipped,
not re-paid for.

If a batch's reply comes back **cut off** — the model ran past its reply length limit partway
through describing a wordy set of assets — that batch is automatically **retried as two smaller
halves**, repeatedly if needed, rather than failing the run. You'll see it in the log as
`Batch 7/7: the reply was cut off… Retrying as two batches of 5 and 6`.

#### Using SF Claude Asset Director

Give it a folder of assets and a brief; it returns the references Claude chose and the prompt
it wrote for them. Wire `images` and `prompt` straight into Nano Banana, Seedream, or anything
else that takes an image batch and a text prompt.

**It decides from a manifest, not from the pixels.** Put a file in the library — `assets.json`
by default, though any text or JSON works — describing what each asset is:

```json
{"assets": [
  {"file": "knight.png", "desc": "Armoured knight character, heroic, front view"},
  {"file": "castle.png", "desc": "Stone castle environment, background location"}
]}
```

That keeps a large library cheap to work with: no image is opened unless you ask for it.

| Input | Purpose |
|---|---|
| `library_path` | The asset folder. Point it at a Google Drive for Desktop sync folder to work off Drive |
| `manifest` | Descriptions file inside the library (default `assets.json`); falls back to filenames if absent |
| `system_prompt` | Standing rules — e.g. *"Choose only character assets unless a background is asked for"* |
| `instruction` | The brief for this run. Type it or wire a string in |
| `max_images` | Ceiling on how many references Claude may pick |
| `pad_to_fit` | **On** (default): scale each image onto a shared canvas, keeping aspect ratios. **Off**: stretch them all to one size |
| `look_at_images` | **Off** (default). On, Claude opens the files as well — better picks on an unlabelled library, but ~5s per image |
| `seed` | Not sent to Claude; change it to force a fresh choice rather than ComfyUI's cached one |

Outputs are `images` (batch), `prompt`, and `picked` (the filenames chosen, for checking its work).

**Why `pad_to_fit` exists:** a ComfyUI image batch is one tensor, so every frame must share
dimensions — and an asset library won't. Padding preserves aspect ratios at the cost of black
bars; stretching avoids bars at the cost of distortion. Which is better depends on the model
you're feeding.

Requires [Claude Code](https://claude.com/claude-code) installed and signed in, same as **SF Claude Code**.

#### Using SF Claude Code

This node shells out to the **Claude Code CLI**, so it bills against your Claude
subscription rather than an Anthropic API key.

**Requirements:** [Claude Code](https://claude.com/claude-code) must be installed *and signed
in* on the machine running ComfyUI. The node searches your `PATH` plus the usual install
locations, and gives a clear error if it can't find it.

| Input | Purpose |
|---|---|
| `prompt` | What you want Claude to do |
| `system_prompt` | Shapes the reply, e.g. *"Reply with only the prompt text, no preamble."* Leave blank to skip |
| `model` | `default`, `opus`, `sonnet`, or `haiku` |
| `timeout_seconds` | Give up after this long (default 300) |
| `seed` | Not sent to Claude — change it to force a fresh reply instead of ComfyUI's cached one |
| `image_1…` | Connect an image and the next slot appears, up to 16 |

Worth knowing before you build a big batch around it:

- **Roughly 5–6 seconds per call minimum.** Claude Code is an agent that reads each image as a
  tool call, so it's slower than a direct vision API request.
- **Subscription rate limits apply.** Heavy batch use will hit them; `SF LLM Chat` with an API
  key is the pay-per-token alternative that won't.
- **Not portable.** Anyone else installing this pack needs their own Claude Code install and
  login for this particular node. Every other node in the pack is unaffected.

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

#### 3D Generation

| Node | Description |
|---|---|
| **SF WaveSpeed Tripo P2 Image to 3D** | Tripo's P2 model — the same one behind ComfyUI's *Tripo P2: Image to Model* partner node — billed to your WaveSpeed account instead of ComfyUI credits. Quad or triangle topology, a target face count, texture quality from none to extreme, PBR, delighting, UVs, and seeds. |

Outputs mirror the partner node, so they plug into **Preview 3D** and **Save 3D** directly: Tripo
returns **FBX when `quad` is on and GLB when it's off**, so the matching output is populated and
the other is empty. The file is also saved to `output/3d/`, with its path and CDN URL as strings.

`face_limit` runs 48–50,000 for triangles or 48–25,000 for quads; `-1` lets Tripo decide. It's a
target, not a hard cap. Leave `export_orientation` unset if the model is headed for rigging or
retexturing — Tripo warns those steps can come out mis-rotated without reporting an error.

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
| **SF Google Sheet Prompt Queue** | Run a batch of prompts straight from a Google Sheet. Reads prompts from one column, skips any row you've marked as finished in a second column, and sends the rest downstream — the graph runs once per prompt. |

**Google Sheet nodes require the sheet to be shared as "Anyone with the link can view."**
The sheet tab GID is found in the browser URL after `#gid=` when you have that tab open.

#### Using SF Google Sheet Prompt Queue

Set your sheet up with prompts in one column and an empty column beside it for tracking:

| | A | B |
|---|---|---|
| **1** | Prompt | Status |
| **2** | a red cat on a windowsill | done |
| **3** | a blue dog in the snow | |
| **4** | a green bird mid-flight | |

With the defaults (`prompt_col` A, `status_col` B, `skip_first_row` on), a run sends rows 3 and 4
and skips row 2. Each prompt triggers a separate pass through the downstream graph.

- **`max_rows`** caps how many prompts go out per run — 10 by default.
- **Marking is manual.** Type anything into the status column — `done`, `x`, `executed` — and that
  row is skipped next time. Clear the cell and it gets queued again.
- **Scanning stops at the first empty prompt cell**, so anything below a gap is ignored.
- **The sheet is re-read on every run**, so edits you make in the browser are picked up
  automatically. Add rows or clear status cells and just hit Run again.
- **Refresh sheet** is optional — it reports how many prompts are pending without running
  the graph.

---

## Interface improvements

Not nodes — small fixes to ComfyUI's own interface that come with the pack.

### Folder picker in the Save workflow dialog

ComfyUI's **Save** / **Save As** dialog normally wants the whole path typed by hand —
`Stillfront/NewMoon/My Workflow` — to save into a subfolder. With this pack installed, the dialog
also shows your workflow folders as a tree: click a folder, type just the name, confirm.

- **+ New folder** adds a folder at the selected level; it's created on disk when you save into it
- The dialog opens on the folder of the workflow you're editing, already selected
- Only the Save dialogs get the picker — Rename and Export, which reuse the same prompt, are left alone
- ComfyUI still does the actual saving, so tab tracking and overwrite warnings behave exactly as before

Turn it off under **Settings → Stillfront → Workflows**.

---

## Requirements

- Python 3.10+
- ComfyUI
- See `requirements.txt` for full Python dependency list

## License

MIT License — see [LICENSE](LICENSE) for details.
