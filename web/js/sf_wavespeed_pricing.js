/**
 * WaveSpeed list prices (USD per run) for the SF WaveSpeed nodes that show a
 * cost badge. Taken from each model's wavespeed.ai page on 2026-10-30; WaveSpeed
 * says those pages can lag, and the task charge is what you actually pay.
 *
 * No imports, so the price maths can be checked outside ComfyUI.
 */

// quality -> [1k, 2k, 4k]
const GPT_25_T2I = {
    low: [0.01, 0.02, 0.03],
    medium: [0.024, 0.04, 0.07],
    high: [0.09, 0.15, 0.27],
    xhigh: [0.16, 0.27, 0.48],
    max: [0.36, 0.6, 1.0],
};
// Includes the first reference image.
const GPT_25_EDIT = {
    low: [0.025, 0.035, 0.045],
    medium: [0.039, 0.055, 0.085],
    high: [0.105, 0.165, 0.285],
    xhigh: [0.175, 0.285, 0.495],
    max: [0.375, 0.615, 1.015],
};
const GPT_2_T2I = {
    low: [0.01, 0.02, 0.03],
    medium: [0.06, 0.1, 0.18],
    high: [0.22, 0.4, 0.72],
};
const GPT_2_EDIT = {
    low: [0.02, 0.03, 0.04],
    medium: [0.07, 0.11, 0.19],
    high: [0.23, 0.41, 0.73],
};
// quality -> [1024x1024, any other size]
const GPT_15_T2I = { low: [0.01, 0.02], medium: [0.04, 0.06], high: [0.14, 0.21] };
const GPT_15_EDIT = { low: [0.02, 0.03], medium: [0.05, 0.07], high: [0.15, 0.21] };

const RESOLUTION_INDEX = { "1k": 0, "2k": 1, "4k": 2 };

/** One GPT Image request. `references` is the number of connected image inputs. */
export function gptImagePrice({ model, quality, resolution, size, input_fidelity, references }) {
    const editing = references > 0;
    const extra = Math.max(references - 1, 0);

    if (model === "gpt-image-1.5") {
        const col = size === "1024x1024" ? 0 : 1;
        if (!editing) return GPT_15_T2I[quality]?.[col];
        const base = GPT_15_EDIT[quality]?.[col];
        if (base == null) return undefined;
        return base + 0.01 * extra + (input_fidelity === "high" ? 0.05 * references : 0);
    }

    const col = RESOLUTION_INDEX[String(resolution).toLowerCase()];
    if (model === "gpt-image-2") {
        const base = (editing ? GPT_2_EDIT : GPT_2_T2I)[quality]?.[col];
        return base == null ? undefined : base + (editing ? 0.012 * extra : 0);
    }
    // gpt-image-2.5-flare and -sunburst share one price list.
    const base = (editing ? GPT_25_EDIT : GPT_25_T2I)[quality]?.[col];
    return base == null ? undefined : base + (editing ? 0.015 * extra : 0);
}

// Same price for text-to-image and edit. Pro's 8K runs on WaveSpeed's "ultra" endpoint.
const NANO_BANANA = {
    "Nano Banana 2.1": { "1k": 0.04, "2k": 0.06, "4k": 0.135 },
    "gemini-3-pro-image-preview": { "1k": 0.14, "2k": 0.14, "4k": 0.24, "8k": 0.18 },
    "Nano Banana 2 (Gemini 3.1 Flash Image)": { "1k": 0.07, "2k": 0.105, "4k": 0.14 },
};
const NANO_BANANA_SEARCH = 0.014; // each of web and image search
const NANO_BANANA_21_PER_REFERENCE = 0.002;

/** `references` counts connected image inputs, not the frames inside a batch. */
export function nanoBananaPrice({ model, resolution, references, enable_web_search, enable_image_search }) {
    const base = NANO_BANANA[model]?.[String(resolution).toLowerCase()];
    if (base == null) return undefined;
    const searches = (enable_web_search ? 1 : 0) + (enable_image_search ? 1 : 0);
    const perReference = model === "Nano Banana 2.1" ? NANO_BANANA_21_PER_REFERENCE : 0;
    return base + NANO_BANANA_SEARCH * searches + perReference * references;
}

// The node switches PBR off along with textures, so 'none' is the untextured price.
const TRIPO_P2 = { none: 1.2, fast: 1.32, standard: 1.32, detailed: 1.44, extreme: 1.56 };

export function tripoP2Price({ texture }) {
    return TRIPO_P2[texture];
}

const TRIPO_H31_TEXTURE = { none: 1, standard: 1.5, detailed: 2 };

export function tripoH31Price({ texture, geometry_quality, quad }) {
    const multiplier = TRIPO_H31_TEXTURE[texture];
    if (multiplier == null) return undefined;
    return 0.24 * multiplier + (geometry_quality === "detailed" ? 0.24 : 0) + (quad ? 0.06 : 0);
}

/** "$0.024", "$0.04", "$1.32": cents always shown, a third decimal only when it matters. */
export function formatUsd(usd) {
    const rounded = Math.round(usd * 1000) / 1000;
    const digits = Math.abs(rounded * 100 - Math.round(rounded * 100)) < 1e-9 ? 2 : 3;
    return `$${rounded.toFixed(digits)}`;
}

// Pro: 1K and 1.5K cost the same; each reference after the first adds $0.003 when editing.
const SEEDREAM_PRO = { "1k": 0.045, "1.5k": 0.045, "2k": 0.09 };
const SEEDREAM_FLASH = 0.027; // any resolution, any number of references

export function seedreamPrice({ model, resolution, references }) {
    if (model === "Seedream 5.0 Flash") return SEEDREAM_FLASH;
    const base = SEEDREAM_PRO[String(resolution).toLowerCase()];
    return base == null ? undefined : base + 0.003 * Math.max(references - 1, 0);
}

// Per second of output video.
const SEEDANCE_PER_SECOND = { "480p": 0.18, "720p": 0.36, "1080p": 0.9, "4k": 1.8 };

export function seedancePrice({ resolution, duration }) {
    const rate = SEEDANCE_PER_SECOND[resolution];
    return rate == null ? undefined : rate * Number(duration);
}

export function rodinPrice({ tier, high_pack }) {
    return (tier === "Gen-2.5-Extreme-High" ? 0.96 : 0.48) + (high_pack ? 0.96 : 0);
}

export function meshyPrice({ should_texture, model_type, geometry_resolution, enable_rigging, enable_animation }) {
    let usd = should_texture ? 1.44 : 0.96;
    if (model_type === "standard") usd += { "2k": 0.24, "4k": 0.48 }[geometry_resolution] ?? 0;
    if (enable_rigging) usd += 0.24 + (enable_animation ? 0.144 : 0);
    return usd;
}
