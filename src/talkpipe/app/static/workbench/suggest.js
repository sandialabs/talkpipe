// Suggestions sidebar: heuristic "likely next" ranking (client-side, from
// /api/suggest/stats) plus LLM suggestions (/api/suggest) with settings.
// The whole panel stays hidden if neither API is available.

import { setHeuristicStats, getReference, cursorContext } from "./editor.js";

const $ = (id) => document.getElementById(id);

let editor = null;
let stats = null;
let llmStatus = { available: false };
let autoSuggest = false;
let autoTimer = null;
let inflight = null;

// --- Heuristic "likely next" ------------------------------------------------

async function refreshStats() {
  try {
    const response = await fetch("/api/suggest/stats");
    if (!response.ok) return false;
    stats = await response.json();
    setHeuristicStats(stats);
    return true;
  } catch (e) {
    return false;
  }
}

function componentType(name) {
  const ref = getReference();
  const comp = ref && ref.byName.get(name);
  if (!comp) return null;
  return comp.type === "source" ? "source" : "segment";
}

// Rank candidates from the stats tables, keeping only the types that are
// grammatically valid at the cursor.
function rankedCandidates(ctx) {
  const validTypes =
    ctx.context === "source_position" ? ["source"]
    : ctx.context === "pipe_stage" || ctx.context === "after_stage" ? ["segment"]
    : ["source", "segment"];

  let ranked = [];
  if (ctx.prev && stats.bigrams && stats.bigrams[ctx.prev]) {
    ranked = Object.entries(stats.bigrams[ctx.prev]).sort((a, b) => b[1] - a[1]);
  } else if (stats.starts) {
    ranked = Object.entries(stats.starts).sort((a, b) => b[1] - a[1]);
  }
  return ranked.filter(([name]) => {
    const type = componentType(name);
    return type && validTypes.includes(type);
  });
}

// The exact text a suggestion click should insert, given the cursor context.
// Mirrors the server's insert_text_for.
function insertTextFor(ctx, name, paramsHint) {
  const params = paramsHint ? `[${paramsHint}]` : "";
  if (ctx.context === "brackets") return paramsHint || "";
  if (ctx.context === "source_position") return `${name}${params}`;
  if (ctx.context === "after_stage") return ` | ${name}${params}`;
  if (ctx.context === "statement_start") {
    return componentType(name) === "source"
      ? `INPUT FROM ${name}${params}`
      : `| ${name}${params}`;
  }
  return `${name}${params}`; // pipe_stage
}

function addSuggestionItem({ label, detail, tooltip, insert }) {
  const item = document.createElement("div");
  item.className = "suggest-item";
  if (detail) {
    const badge = document.createElement("span");
    badge.className = "seg-count";
    badge.textContent = detail;
    if (tooltip) badge.title = tooltip;
    item.appendChild(badge);
  }
  const nameSpan = document.createElement("span");
  nameSpan.className = "seg-name";
  nameSpan.textContent = label;
  item.appendChild(nameSpan);
  item.addEventListener("click", () => editor.insertAtCursor(insert));
  return item;
}

function renderHeuristics() {
  const list = $("heuristicList");
  list.textContent = "";
  if (!stats) return;

  const ctx = cursorContext(editor.view);

  // Inside [...]: the useful "likely next" items are the unused parameters
  // of the enclosing component, not other components.
  if (ctx.context === "brackets") {
    const ref = getReference();
    const comp = ref && ref.byName.get(ctx.enclosing || "");
    if (!comp) return;
    for (const p of comp.params.slice(0, 8)) {
      list.appendChild(addSuggestionItem({
        label: `${p.name}=`,
        detail: p.type || "",
        tooltip: p.description || "",
        insert: `${p.name}=`,
      }));
    }
    return;
  }

  const ranked = rankedCandidates(ctx);
  if (ranked.length === 0) {
    const empty = document.createElement("div");
    empty.className = "suggest-status";
    empty.textContent = ctx.prev
      ? `No history for what follows "${ctx.prev}" yet.`
      : "Save some pipelines to build up suggestions.";
    list.appendChild(empty);
    return;
  }

  for (const [name, count] of ranked.slice(0, 8)) {
    const insert = insertTextFor(ctx, name, "");
    list.appendChild(addSuggestionItem({
      label: insert.trim() || name,
      detail: `×${count}`,
      tooltip: "How often this appears here in saved pipelines and examples",
      insert,
    }));
  }
}

// --- LLM suggestions ---------------------------------------------------------

async function fetchLlmStatus() {
  try {
    const response = await fetch("/api/settings");
    if (!response.ok) return null;
    return await response.json();
  } catch (e) {
    return null;
  }
}

function setLlmStatusText(text) {
  $("llmSuggestStatus").textContent = text;
}

async function requestSuggestions() {
  if (!llmStatus.available) return;
  if (inflight) inflight.abort();
  inflight = new AbortController();
  setLlmStatusText("Asking the model…");
  $("llmSuggestList").textContent = "";
  try {
    const response = await fetch("/api/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        script: editor.getValue(),
        cursor_offset: editor.getCursorOffset(),
        max_suggestions: 4,
      }),
      signal: inflight.signal,
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = await response.json();
    if (!data.available) {
      setLlmStatusText(data.error
        ? `LLM unavailable: ${data.error}`
        : "No LLM configured — set one in Settings (⚙).");
      return;
    }
    if (data.error) {
      setLlmStatusText(`Model error: ${data.error}`);
      return;
    }
    renderLlmSuggestions(data);
  } catch (e) {
    if (e.name !== "AbortError") setLlmStatusText("Suggestion request failed.");
  } finally {
    inflight = null;
  }
}

function renderLlmSuggestions(data) {
  const list = $("llmSuggestList");
  list.textContent = "";
  if (data.suggestions.length === 0) {
    setLlmStatusText("The model had no suggestions.");
    return;
  }
  setLlmStatusText(`${data.source} / ${data.model}`);
  const seen = new Set();
  for (const s of data.suggestions) {
    if (seen.has(s.segment)) continue;
    seen.add(s.segment);
    const item = document.createElement("div");
    item.className = "suggest-item";
    const nameSpan = document.createElement("span");
    nameSpan.className = "seg-name";
    nameSpan.textContent = s.segment;
    const rationale = document.createElement("div");
    rationale.className = "seg-rationale";
    rationale.textContent = s.rationale || "";
    item.append(nameSpan, rationale);
    item.addEventListener("click", () => {
      // Recompute the insert text at click time — the cursor may have moved
      // since the suggestion was requested. The server-computed s.insert is
      // the fallback when the reference hasn't loaded yet.
      const insert = getReference()
        ? insertTextFor(cursorContext(editor.view), s.segment, s.params_hint)
        : (s.insert || s.segment);
      editor.insertAtCursor(insert);
    });
    list.appendChild(item);
  }
}

// --- Settings dialog ----------------------------------------------------------

async function openSettings() {
  const settings = await fetchLlmStatus();
  if (!settings) return;

  const sourceSelect = $("settingSource");
  sourceSelect.textContent = "";
  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = "(default)";
  sourceSelect.appendChild(defaultOption);
  for (const s of settings.known_sources || []) {
    const option = document.createElement("option");
    option.value = s;
    option.textContent = s;
    sourceSelect.appendChild(option);
  }
  sourceSelect.value = settings.suggest_source || "";
  $("settingModel").value = settings.suggest_model || "";
  $("settingAutoSuggest").checked = !!settings.auto_suggest;
  const resolved = settings.resolved || {};
  $("settingsResolved").textContent = resolved.available
    ? `Currently using: ${resolved.source} / ${resolved.model}`
    : "No LLM currently available." + (resolved.reason ? ` (${resolved.reason})` : "");

  const dialog = $("settingsDialog");
  dialog.returnValue = "cancel";
  dialog.addEventListener(
    "close",
    async () => {
      if (dialog.returnValue !== "save") return;
      const response = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          suggest_source: sourceSelect.value || null,
          suggest_model: $("settingModel").value.trim() || null,
          auto_suggest: $("settingAutoSuggest").checked,
        }),
      });
      if (response.ok) {
        const updated = await response.json();
        applySettings(updated);
      }
    },
    { once: true }
  );
  dialog.showModal();
}

function applySettings(settings) {
  autoSuggest = !!settings.auto_suggest;
  llmStatus = settings.resolved || { available: false };
  if (llmStatus.available) {
    setLlmStatusText(`Ready: ${llmStatus.source} / ${llmStatus.model}`);
  } else if (llmStatus.reason && llmStatus.reason !== "no model configured") {
    setLlmStatusText(`LLM unavailable: ${llmStatus.reason}`);
  } else {
    setLlmStatusText("No LLM configured — set one in Settings (⚙).");
  }
}

// --- Change notifications ------------------------------------------------------

export function notifyScriptChanged() {
  if (!stats && !llmStatus.available) return;
  renderHeuristics();
  if (autoSuggest && llmStatus.available) {
    clearTimeout(autoTimer);
    autoTimer = setTimeout(requestSuggestions, 2000);
  }
}

// Cursor moves change what is grammatically valid, so the heuristic list
// re-ranks — but they never trigger LLM calls.
export function notifyCursorMoved() {
  if (stats) renderHeuristics();
}

// --- Init ------------------------------------------------------------------------

export async function initSuggestions(editorHandle) {
  editor = editorHandle;
  const hasStats = await refreshStats();
  const settings = await fetchLlmStatus();

  if (!hasStats && !settings) return; // neither API exists: stay hidden

  $("suggest-panel").classList.remove("hidden");
  renderHeuristics();

  if (settings) {
    $("settingsButton").hidden = false;
    $("settingsButton").addEventListener("click", openSettings);
    applySettings(settings);
    $("suggestButton").addEventListener("click", requestSuggestions);
  } else {
    $("llmSuggestSection").classList.add("hidden");
    $("suggestButton").classList.add("hidden");
  }

  // Stats change after saves; refresh when the pipeline list mutates.
  document.addEventListener("workbench:saved", async () => {
    await refreshStats();
    renderHeuristics();
  });
}
