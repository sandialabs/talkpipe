// Pipeline workspace browser: list/open/save/rename/delete saved pipelines
// via /api/pipelines. The whole panel stays hidden if the API is absent.

const $ = (id) => document.getElementById(id);

let editor = null;
let currentId = null;
let currentName = "";
let currentDescription = "";
let dirty = false;
let available = false;

export function markDirty() {
  if (!available || dirty) return;
  dirty = true;
  updateNameLabel();
}

// Styled stand-in for window.confirm()/alert(): resolves true when the user
// accepts. Native dialogs are avoided so the UI stays consistent (and
// automatable). Pass okOnly for alert-style messages.
function confirmDialog(message, { title = "Confirm", okLabel = "OK", okOnly = false } = {}) {
  return new Promise((resolve) => {
    const dialog = $("confirmDialog");
    $("confirmDialogTitle").textContent = title;
    $("confirmDialogMessage").textContent = message;
    $("confirmDialogOk").textContent = okLabel;
    $("confirmDialogCancel").hidden = okOnly;
    dialog.returnValue = "cancel";
    dialog.addEventListener(
      "close",
      () => resolve(dialog.returnValue === "ok"),
      { once: true }
    );
    dialog.showModal();
  });
}

function updateNameLabel() {
  const label = $("pipelineName");
  label.textContent = currentName || "";
  label.classList.toggle("dirty", dirty && !!currentId);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch (e) { /* not json */ }
    const err = new Error(detail);
    err.status = response.status;
    throw err;
  }
  return response.status === 204 ? null : response.json();
}

async function refreshList() {
  const data = await api("/api/pipelines");
  const list = $("pipelineList");
  list.textContent = "";
  if (data.pipelines.length === 0) {
    const empty = document.createElement("div");
    empty.className = "panel-empty";
    empty.textContent = "No saved pipelines yet. Use Save As to add one.";
    list.appendChild(empty);
    return;
  }
  for (const p of data.pipelines) {
    const item = document.createElement("div");
    item.className = "pipeline-item" + (p.id === currentId ? " selected" : "");
    item.title = `modified ${p.modified}`;

    const actions = document.createElement("span");
    actions.className = "item-actions";
    const renameBtn = document.createElement("button");
    renameBtn.className = "icon-button";
    renameBtn.textContent = "✏";
    renameBtn.title = "Rename";
    renameBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      renamePipeline(p);
    });
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "icon-button";
    deleteBtn.textContent = "🗑";
    deleteBtn.title = "Delete";
    deleteBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      deletePipeline(p);
    });
    actions.append(renameBtn, deleteBtn);

    const name = document.createElement("div");
    name.className = "item-name";
    name.textContent = p.name;
    const description = document.createElement("div");
    description.className = "item-description";
    description.textContent = p.description || "";

    item.append(actions, name, description);
    item.addEventListener("click", () => openPipeline(p.id));
    list.appendChild(item);
  }
}

async function confirmDiscardIfDirty() {
  if (!dirty || !editor.getValue().trim()) return true;
  const what = currentId ? "the current pipeline" : "the editor";
  return confirmDialog(`Discard unsaved changes to ${what}?`, {
    title: "Unsaved changes", okLabel: "Discard",
  });
}

async function openPipeline(id) {
  if (!(await confirmDiscardIfDirty())) return;
  const p = await api(`/api/pipelines/${id}`);
  editor.setValue(p.script);
  currentId = p.id;
  currentName = p.name;
  currentDescription = p.description || "";
  dirty = false;
  updateNameLabel();
  refreshList();
}

// Replace the editor content without attaching it to any saved pipeline
// (used by the Examples menu). Asks before discarding unsaved work.
export async function loadIntoScratch(code) {
  if (available && !(await confirmDiscardIfDirty())) return false;
  editor.setValue(code);
  if (available) {
    currentId = null;
    currentName = "";
    currentDescription = "";
    dirty = false;
    updateNameLabel();
    refreshList();
  }
  return true;
}

function showSaveDialog(title, name, description) {
  return new Promise((resolve) => {
    const dialog = $("saveDialog");
    $("saveDialogTitle").textContent = title;
    $("saveName").value = name || "";
    $("saveDescription").value = description || "";
    dialog.returnValue = "cancel";
    dialog.addEventListener(
      "close",
      () => {
        if (dialog.returnValue !== "save") return resolve(null);
        resolve({
          name: $("saveName").value.trim(),
          description: $("saveDescription").value.trim(),
        });
      },
      { once: true }
    );
    dialog.showModal();
  });
}

function notifySaved() {
  document.dispatchEvent(new CustomEvent("workbench:saved"));
}

async function saveCurrent() {
  if (!currentId) return saveAs();
  await api(`/api/pipelines/${currentId}`, {
    method: "PUT",
    body: JSON.stringify({ script: editor.getValue() }),
  });
  dirty = false;
  updateNameLabel();
  refreshList();
  notifySaved();
}

function adoptSaved(p) {
  currentId = p.id;
  currentName = p.name;
  currentDescription = p.description || "";
  dirty = false;
  updateNameLabel();
  refreshList();
  notifySaved();
}

async function saveAs() {
  let name = currentName;
  let description = currentDescription;
  // Loop so declining an overwrite returns to the Save-As dialog with the
  // typed name/description intact instead of throwing the input away.
  for (;;) {
    const meta = await showSaveDialog("Save pipeline as", name, description);
    if (!meta || !meta.name) return;
    ({ name, description } = meta);
    try {
      adoptSaved(await api("/api/pipelines", {
        method: "POST",
        body: JSON.stringify({ ...meta, script: editor.getValue() }),
      }));
      return;
    } catch (e) {
      if (e.status === 409) {
        const overwrite = await confirmDialog(
          `"${meta.name}" already exists. Overwrite it?`,
          { title: "Pipeline exists", okLabel: "Overwrite" }
        );
        if (!overwrite) continue;
        adoptSaved(await api("/api/pipelines", {
          method: "POST",
          body: JSON.stringify({ ...meta, script: editor.getValue(), overwrite: true }),
        }));
        return;
      }
      await confirmDialog("Save failed: " + e.message, {
        title: "Save failed", okOnly: true,
      });
      return;
    }
  }
}

async function renamePipeline(p) {
  const meta = await showSaveDialog("Rename pipeline", p.name, p.description || "");
  if (!meta || !meta.name) return;
  let updated = p;
  try {
    if (meta.name !== p.name) {
      updated = await api(`/api/pipelines/${p.id}/rename`, {
        method: "POST",
        body: JSON.stringify({ new_name: meta.name }),
      });
    }
    if ((meta.description || "") !== (p.description || "")) {
      updated = await api(`/api/pipelines/${updated.id}`, {
        method: "PUT",
        body: JSON.stringify({ description: meta.description }),
      });
    }
  } catch (e) {
    await confirmDialog("Rename failed: " + e.message, {
      title: "Rename failed", okOnly: true,
    });
    return;
  }
  if (currentId === p.id) {
    currentId = updated.id;
    currentName = updated.name;
    currentDescription = updated.description || "";
    updateNameLabel();
  }
  refreshList();
}

async function deletePipeline(p) {
  const proceed = await confirmDialog(`Delete pipeline "${p.name}"?`, {
    title: "Delete pipeline", okLabel: "Delete",
  });
  if (!proceed) return;
  await api(`/api/pipelines/${p.id}`, { method: "DELETE" });
  notifySaved();
  if (currentId === p.id) {
    currentId = null;
    currentName = "";
    currentDescription = "";
    dirty = false;
    updateNameLabel();
  }
  refreshList();
}

export async function initWorkspace(editorHandle) {
  editor = editorHandle;
  try {
    await refreshList();
  } catch (e) {
    return; // API absent: leave the panel and buttons hidden
  }
  available = true;
  $("pipelines-panel").classList.remove("hidden");
  $("saveButton").hidden = false;
  $("saveAsButton").hidden = false;
  $("saveButton").addEventListener("click", saveCurrent);
  $("saveAsButton").addEventListener("click", saveAs);
  $("refreshPipelines").addEventListener("click", refreshList);
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "s") {
      event.preventDefault();
      saveCurrent();
    }
  });
}
