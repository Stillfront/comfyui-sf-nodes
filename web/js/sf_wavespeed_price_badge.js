/**
 * SF WaveSpeed price badge — shows the estimated WaveSpeed cost in dollars in
 * the node header, updating as the settings change.
 *
 * ComfyUI's own price badge only renders on Comfy partner (api_node) nodes, and
 * marking ours as such would make ComfyUI treat them as Comfy-billed. So the
 * classic canvas gets an ordinary extension badge, and Vue nodes get a pill
 * added to their header.
 */

import { app } from "../../../scripts/app.js";
import {
    formatUsd,
    gptImagePrice,
    meshyPrice,
    nanoBananaPrice,
    rodinPrice,
    seedancePrice,
    seedreamPrice,
    tripoH31Price,
    tripoP2Price,
} from "./sf_wavespeed_pricing.js";

/** Widget value by name. V3 dynamic combos prefix their child widgets, e.g. "model.quality". */
function widgetValue(node, name) {
    const widget = node.widgets?.find((w) => w.name === name || w.name?.endsWith(`.${name}`));
    return widget?.value;
}

function connectedImages(node) {
    return (node.inputs ?? []).filter((input) => input.type === "IMAGE" && input.link != null).length;
}

// node type -> () => { usd, count } for one run of the node
const PRICERS = {
    SFWaveSpeedGPTImage: (node) => ({
        usd: gptImagePrice({
            model: widgetValue(node, "model"),
            quality: widgetValue(node, "quality"),
            resolution: widgetValue(node, "resolution"),
            size: widgetValue(node, "size"),
            input_fidelity: widgetValue(node, "input_fidelity"),
            references: connectedImages(node),
        }),
        count: Number(widgetValue(node, "n")) || 1,
    }),
    SFWaveSpeedNanoBananaPro: (node) => ({
        usd: nanoBananaPrice({
            model: widgetValue(node, "model"),
            resolution: widgetValue(node, "resolution"),
            references: connectedImages(node),
            enable_web_search: widgetValue(node, "enable_web_search"),
            enable_image_search: widgetValue(node, "enable_image_search"),
        }),
        count: Number(widgetValue(node, "n")) || 1,
    }),
    SFWaveSpeedSeedreamV5: (node) => ({
        usd: seedreamPrice({
            model: widgetValue(node, "model"),
            resolution: widgetValue(node, "resolution"),
            references: connectedImages(node),
        }),
        count: Number(widgetValue(node, "n")) || 1,
    }),
    SFWaveSpeedSeedanceV25: (node) => ({
        usd: seedancePrice({
            resolution: widgetValue(node, "resolution"),
            duration: widgetValue(node, "duration"),
        }),
        count: 1,
    }),
    SFWaveSpeedRodinV25ImageTo3D: (node) => ({
        usd: rodinPrice({ tier: widgetValue(node, "tier"), high_pack: widgetValue(node, "high_pack") }),
        count: 1,
    }),
    SFWaveSpeedMeshyV71ImageTo3D: (node) => ({
        usd: meshyPrice({
            should_texture: widgetValue(node, "should_texture"),
            model_type: widgetValue(node, "model_type"),
            geometry_resolution: widgetValue(node, "geometry_resolution"),
            enable_rigging: widgetValue(node, "enable_rigging"),
            enable_animation: widgetValue(node, "enable_animation"),
        }),
        count: 1,
    }),
    SFWaveSpeedTripoP2ImageTo3D: (node) => ({
        usd: tripoP2Price({ texture: widgetValue(node, "texture") }),
        count: 1,
    }),
    SFWaveSpeedTripoH31ImageTo3D: (node) => ({
        usd: tripoH31Price({
            texture: widgetValue(node, "texture"),
            geometry_quality: widgetValue(node, "geometry_quality"),
            quad: widgetValue(node, "quad"),
        }),
        count: 1,
    }),
};

function badgeText(node, pricer) {
    const { usd, count } = pricer(node);
    if (usd == null) return "";
    const total = `~${formatUsd(usd * count)}/run`;
    return count > 1 ? `${total} (${count} × ${formatUsd(usd)})` : total;
}

/**
 * Duck-types LiteGraph's LGraphBadge (text, height, getWidth, draw) so the
 * classic canvas can draw it without depending on an internal class.
 */
class PriceBadge {
    constructor(getText) {
        this.getText = getText;
        this.height = 20;
        this.fgColor = "#f5f5f5";
        this.bgColor = "#2b6a3f";
    }

    get text() {
        return this.getText();
    }

    getWidth(ctx) {
        const text = this.text;
        if (!text) return 0;
        ctx.save();
        ctx.font = "12px sans-serif";
        const width = ctx.measureText(text).width + 12;
        ctx.restore();
        return width;
    }

    draw(ctx, x, y) {
        const text = this.text;
        if (!text) return;
        const width = this.getWidth(ctx);
        ctx.save();
        ctx.fillStyle = this.bgColor;
        ctx.beginPath();
        ctx.roundRect(x, y, width, this.height, 5);
        ctx.fill();
        ctx.fillStyle = this.fgColor;
        ctx.font = "12px sans-serif";
        ctx.textBaseline = "middle";
        ctx.fillText(text, x + 6, y + this.height / 2 + 1);
        ctx.restore();
    }
}

/**
 * The Vue node header only renders ComfyUI's own credit badges, so on Vue
 * nodes the price is added to the header element directly. Polled rather than
 * event-driven: Vue can rebuild a header at any time, and widget edits do not
 * reach extensions through one reliable hook.
 */
function syncVueHeaders() {
    for (const node of app.canvas?.graph?.nodes ?? []) {
        const pricer = PRICERS[node.type];
        if (!pricer) continue;
        const header = document.querySelector(`[data-testid="node-header-${node.id}"]`);
        const row = header?.firstElementChild;
        if (!row) continue;

        let pill = row.querySelector(":scope > [data-sf-price]");
        if (!pill) {
            pill = document.createElement("span");
            pill.dataset.sfPrice = "";
            pill.title = "Estimated WaveSpeed cost from wavespeed.ai list prices";
            Object.assign(pill.style, {
                flexShrink: "0",
                whiteSpace: "nowrap",
                fontSize: "11px",
                lineHeight: "16px",
                padding: "1px 6px",
                marginRight: "4px",
                borderRadius: "6px",
                color: "#d7f5df",
                background: "rgba(43, 106, 63, 0.85)",
            });
            row.appendChild(pill);
        }
        const text = badgeText(node, pricer);
        if (pill.textContent !== text) pill.textContent = text;
        pill.style.display = text ? "" : "none";
    }
}

app.registerExtension({
    name: "SF.WaveSpeedPriceBadge",
    setup() {
        setInterval(syncVueHeaders, 250);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const pricer = PRICERS[nodeData.name];
        if (!pricer) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            const badge = new PriceBadge(() => badgeText(this, pricer));
            // A getter, so the text is recomputed whenever the header redraws.
            this.badges = [...(this.badges ?? []), () => badge];
            return result;
        };
    },
});
