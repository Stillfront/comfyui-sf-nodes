/**
 * SF Claude Code — grows the image input list on demand.
 *
 * The Python side declares image_1..image_16 as optional inputs. This keeps
 * only as many slots visible as are in use, plus one spare to connect into.
 */

import { app } from "../../../scripts/app.js";

const NODE_NAME = "SFClaudeCode";
const MAX_IMAGES = 16;

function imageSlotIndex(node, n) {
    return (node.inputs ?? []).findIndex((input) => input.name === `image_${n}`);
}

function syncImageSlots(node) {
    if (!node.inputs) {
        return;
    }

    // Highest numbered image slot that currently has something plugged in.
    let lastUsed = 0;
    for (const input of node.inputs) {
        const match = input.name?.match(/^image_(\d+)$/);
        if (match && input.link != null) {
            lastUsed = Math.max(lastUsed, parseInt(match[1], 10));
        }
    }

    // Show every used slot, plus one empty spare to drag into.
    const wanted = Math.min(lastUsed + 1, MAX_IMAGES);

    for (let n = 1; n <= wanted; n++) {
        if (imageSlotIndex(node, n) === -1) {
            node.addInput(`image_${n}`, "IMAGE");
        }
    }

    // Drop trailing spares, but never one that is still connected.
    for (let n = MAX_IMAGES; n > wanted; n--) {
        const index = imageSlotIndex(node, n);
        if (index !== -1 && node.inputs[index].link == null) {
            node.removeInput(index);
        }
    }

    node.setSize(node.computeSize());
    node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "Stillfront.ClaudeCode",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            syncImageSlots(this);
            return result;
        };

        // Re-sync after a saved workflow restores its connections.
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            requestAnimationFrame(() => syncImageSlots(this));
            return result;
        };

        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected, linkInfo, ioSlot) {
            const result = onConnectionsChange
                ? onConnectionsChange.apply(this, arguments)
                : undefined;
            // Let litegraph finish updating link state before recounting.
            requestAnimationFrame(() => syncImageSlots(this));
            return result;
        };
    },
});
