/**
 * SF Save Folder Picker — adds a folder browser to ComfyUI's "Save workflow"
 * dialog, so a workflow can be saved into a subfolder by clicking the folder
 * and typing only the name, instead of typing the whole path.
 *
 * It augments the native dialog rather than replacing it: ComfyUI still does
 * the actual saving, so tab tracking and overwrite confirmation are unchanged.
 * Picking a folder only rewrites the path in the dialog's own input.
 */

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const SETTING_ID = "Stillfront.SaveFolderPicker";
const SAVE_COMMANDS = ["Comfy.SaveWorkflow", "Comfy.SaveWorkflowAs"];
const ROOT = "workflows";

// True only while a Save command is running, so the same prompt dialog used
// for renaming or exporting is left alone.
let savePending = false;

function enabled() {
    try {
        return app.extensionManager?.setting?.get(SETTING_ID) !== false;
    } catch {
        return true;
    }
}

async function fetchFolders() {
    const res = await api.fetchApi(`/v2/userdata?path=${encodeURIComponent(ROOT)}`);
    if (!res.ok) {
        throw new Error(`folder list failed (${res.status})`);
    }
    const entries = await res.json();
    return entries
        .filter((e) => e.type === "directory")
        .map((e) => e.path.replace(/^workflows\/?/, ""))
        .filter((p) => p && !p.split("/").some((part) => part.startsWith(".")))
        .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
}

function el(tag, style = "", text = "") {
    const node = document.createElement(tag);
    if (style) node.style.cssText = style;
    if (text) node.textContent = text;
    return node;
}

function splitPath(value) {
    const i = value.lastIndexOf("/");
    return i === -1 ? { folder: "", name: value } : { folder: value.slice(0, i), name: value.slice(i + 1) };
}

function setInput(input, folder) {
    const { name } = splitPath(input.value);
    input.value = folder ? `${folder}/${name}` : name;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
    // Select just the name, ready to be typed over.
    const start = input.value.length - name.length;
    input.setSelectionRange(start, input.value.length);
}

function buildPicker(input, folders) {
    const expanded = new Set();
    let selected = splitPath(input.value).folder;

    // Open the branch leading to the folder the dialog started in.
    selected.split("/").reduce((acc, part) => {
        const path = acc ? `${acc}/${part}` : part;
        if (part) expanded.add(path);
        return path;
    }, "");

    const box = el(
        "div",
        "border:1px solid rgba(128,128,128,.35);border-radius:6px;margin:4px 0 8px;"
    );
    const header = el(
        "div",
        "display:flex;align-items:center;justify-content:space-between;padding:6px 8px;" +
            "font-size:12px;opacity:.75;border-bottom:1px solid rgba(128,128,128,.25);"
    );
    header.appendChild(el("span", "", "Save into folder"));
    const newBtn = el(
        "button",
        "background:none;border:1px solid rgba(128,128,128,.4);border-radius:4px;" +
            "padding:2px 8px;font-size:12px;color:inherit;cursor:pointer;",
        "+ New folder"
    );
    newBtn.type = "button";
    header.appendChild(newBtn);
    box.appendChild(header);

    const list = el("div", "max-height:260px;overflow-y:auto;padding:4px 0;font-size:13px;");
    box.appendChild(list);

    const hasChildren = (path) => folders.some((f) => f.startsWith(`${path}/`));
    const childrenOf = (parent) =>
        folders.filter((f) => {
            const { folder } = splitPath(f);
            return folder === parent;
        });

    function row(path, depth) {
        const label = path ? splitPath(path).name : `${ROOT} (top level)`;
        const r = el(
            "div",
            `display:flex;align-items:center;gap:4px;padding:3px 8px 3px ${8 + depth * 16}px;` +
                "cursor:pointer;border-radius:4px;user-select:none;" +
                (path === selected ? "background:rgba(66,133,244,.28);" : "")
        );
        const caret = el("span", "width:14px;display:inline-block;text-align:center;opacity:.7;");
        if (path && hasChildren(path)) {
            caret.textContent = expanded.has(path) ? "▾" : "▸";
            caret.addEventListener("click", (e) => {
                e.stopPropagation();
                expanded.has(path) ? expanded.delete(path) : expanded.add(path);
                render();
            });
        }
        r.appendChild(caret);
        r.appendChild(el("span", "", `📁 ${label}`));
        r.addEventListener("mouseenter", () => {
            if (path !== selected) r.style.background = "rgba(128,128,128,.15)";
        });
        r.addEventListener("mouseleave", () => {
            if (path !== selected) r.style.background = "";
        });
        r.addEventListener("click", () => {
            selected = path;
            setInput(input, path);
            render();
        });
        return r;
    }

    function addBranch(parent, depth) {
        for (const child of childrenOf(parent)) {
            list.appendChild(row(child, depth));
            if (expanded.has(child)) addBranch(child, depth + 1);
        }
    }

    function render() {
        list.replaceChildren(row("", 0));
        addBranch("", 1);
    }

    newBtn.addEventListener("click", () => {
        const where = selected ? `inside "${selected}"` : "at the top level";
        const name = window.prompt(`New folder name (${where}):`);
        const clean = (name || "").trim().replace(/[\\/]+/g, "-");
        if (!clean) return;
        const path = selected ? `${selected}/${clean}` : clean;
        // The folder is created on disk when the workflow is saved into it.
        if (!folders.includes(path)) folders.push(path);
        folders.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
        if (selected) expanded.add(selected);
        selected = path;
        setInput(input, path);
        render();
    });

    render();
    return box;
}

async function inject(dialog) {
    if (dialog.dataset.sfFolderPicker) return;
    dialog.dataset.sfFolderPicker = "1";

    const input = dialog.querySelector("input");
    if (!input) return;

    let picker;
    try {
        picker = buildPicker(input, await fetchFolders());
    } catch (e) {
        picker = el("div", "font-size:12px;opacity:.7;margin:4px 0;", `Folder list unavailable: ${e.message}`);
    }
    input.parentElement.insertBefore(picker, input);
}

app.registerExtension({
    name: "Stillfront.SaveFolderPicker",

    settings: [
        {
            id: SETTING_ID,
            category: ["Stillfront", "Workflows", "Folder picker in Save dialog"],
            name: "Show a folder browser in the Save workflow dialog",
            type: "boolean",
            defaultValue: true,
        },
    ],

    async setup() {
        const commands = app.extensionManager?.command?.commands || [];
        for (const id of SAVE_COMMANDS) {
            const command = commands.find((c) => c.id === id);
            if (!command) continue;
            const original = command.function;
            command.function = async function () {
                savePending = true;
                try {
                    return await original.apply(this, arguments);
                } finally {
                    savePending = false;
                }
            };
        }

        new MutationObserver(() => {
            if (!savePending || !enabled()) return;
            const dialog = document.querySelector(".prompt-dialog-content:not([data-sf-folder-picker])");
            if (dialog) inject(dialog);
        }).observe(document.body, { childList: true, subtree: true });
    },
});
