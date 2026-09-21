/**
 * SF Google Sheet Prompt Queue — adds a Refresh button that re-reads the sheet
 * and reports how many prompts are still waiting to run.
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_NAME = "SFGoogleSheetPromptQueue";

function widgetValue(node, name, fallback) {
    const widget = node.widgets?.find((w) => w.name === name);
    return widget ? widget.value : fallback;
}

app.registerExtension({
    name: "Stillfront.GoogleSheetPromptQueue",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            const node = this;

            const status = node.addWidget("text", "", "Press Refresh to read the sheet", () => {});
            status.disabled = true;
            status.serialize = false;

            const setStatus = (text) => {
                status.value = text;
                node.setDirtyCanvas(true, false);
            };

            const refreshButton = node.addWidget("button", "Refresh sheet", null, async () => {
                setStatus("Reading sheet…");
                try {
                    const response = await api.fetchApi("/sf_gsheet/preview", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            url: widgetValue(node, "url", ""),
                            sheet_gid: widgetValue(node, "sheet_gid", "0"),
                            prompt_col: widgetValue(node, "prompt_col", "A"),
                            status_col: widgetValue(node, "status_col", "B"),
                            skip_first_row: widgetValue(node, "skip_first_row", true),
                        }),
                    });
                    const data = await response.json();

                    if (!data.ok) {
                        setStatus(`Error: ${data.error}`);
                        return;
                    }

                    const cap = widgetValue(node, "max_rows", 10);
                    const willSend = Math.min(data.pending, cap);
                    setStatus(
                        data.pending === 0
                            ? `Nothing pending — all ${data.total} prompt(s) marked`
                            : `${data.pending} pending of ${data.total} — next run sends ${willSend}`
                    );
                } catch (e) {
                    setStatus("Could not reach ComfyUI server");
                }
            });
            refreshButton.serialize = false;

            return result;
        };
    },
});
