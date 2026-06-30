/**
 * Dynamic Prompt List - Hide widgets beyond inputcount using computeSize
 */

import { app } from "../../../scripts/app.js";

app.registerExtension({
    name: "Serhii.DynamicPromptList",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "Dynamic Prompt List") {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

            const self = this;

            // Override computeSize to hide widgets beyond inputcount
            const originalComputeSize = this.computeSize;
            this.computeSize = function(out) {
                const inputcountWidget = this.widgets?.find(w => w.name === "inputcount");
                const targetCount = inputcountWidget ? inputcountWidget.value : 5;

                // Hide widgets beyond targetCount by setting computeSize to 0
                this.widgets.forEach(widget => {
                    if (widget.name && widget.name.startsWith("prompt_")) {
                        const promptNum = parseInt(widget.name.split("_")[1]);
                        if (promptNum > targetCount) {
                            // Hide this widget
                            widget.computeSize = () => [0, -4];
                            widget.hidden = true;
                        } else {
                            // Show this widget
                            delete widget.computeSize;
                            widget.hidden = false;
                        }
                    }
                });

                // Call original computeSize
                return originalComputeSize ? originalComputeSize.call(this, out) : [200, 100];
            };

            // Hook into inputcount changes
            const inputcountWidget = this.widgets.find(w => w.name === "inputcount");
            if (inputcountWidget) {
                const originalCallback = inputcountWidget.callback;
                inputcountWidget.callback = function(value) {
                    if (originalCallback) {
                        originalCallback.apply(this, arguments);
                    }
                    // Force recompute
                    self.setSize(self.computeSize());
                    self.setDirtyCanvas(true, true);
                };
            }

            // Initial size calculation
            this.setSize(this.computeSize());

            return r;
        };
    }
});
