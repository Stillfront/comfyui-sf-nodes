/**
 * Dynamic Image Inputs for SF VertexAI Nano Banana Pro Edit
 * Uses inputcount and "Update inputs" button to dynamically add/remove image slots.
 * Follows KJNodes JoinStringMulti pattern.
 * Supports up to 14 images as per Gemini 3 Pro Image API.
 */

import { app } from "../../../scripts/app.js";

const NODE_NAME = "SFVertexAINanaBananaProEdit";

app.registerExtension({
  name: "Stillfront.NanaBananaDynamicInputs",

  async beforeRegisterNodeDef(nodeType, nodeData, app) {
    if (nodeData.name !== NODE_NAME) {
      return;
    }

    // Store the input type for dynamic creation
    nodeType.prototype._type = "IMAGE";

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onNodeCreated
        ? onNodeCreated.apply(this, arguments)
        : undefined;

      // Add "Update inputs" button (KJNodes pattern)
      this.addWidget("button", "Update inputs", null, () => {
        if (!this.inputs) {
          this.inputs = [];
        }

        const target_number_of_inputs = this.widgets.find(
          (w) => w.name === "inputcount",
        )["value"];

        // Count current image inputs (exact match for image_N pattern, not image_size etc)
        const num_inputs = this.inputs.filter(
          (input) => input.name && /^image_\d+$/.test(input.name),
        ).length;

        // Debug logging
        console.log(
          `[NanaBanana] Target: ${target_number_of_inputs}, Current: ${num_inputs}`,
        );
        console.log(
          `[NanaBanana] Current inputs:`,
          this.inputs.map((i) => i.name),
        );

        // Already at target, do nothing
        if (target_number_of_inputs === num_inputs) return;

        if (target_number_of_inputs < num_inputs) {
          // Remove inputs from the end
          const inputs_to_remove = num_inputs - target_number_of_inputs;
          for (let i = 0; i < inputs_to_remove; i++) {
            // Find and remove the last image input
            for (let j = this.inputs.length - 1; j >= 0; j--) {
              if (
                this.inputs[j].name &&
                this.inputs[j].name.startsWith("image_")
              ) {
                this.removeInput(j);
                break;
              }
            }
          }
        } else {
          // Add new inputs
          for (let i = num_inputs + 1; i <= target_number_of_inputs; ++i) {
            this.addInput(`image_${i}`, this._type);
          }
        }

        // Mark canvas as dirty without resizing
        this.setDirtyCanvas(true, true);
      });

      return r;
    };
  },
});
