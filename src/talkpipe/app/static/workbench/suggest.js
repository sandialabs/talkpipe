// Suggestions sidebar: heuristic "likely next" ranking (client-side, from
// /api/suggest/stats) plus LLM suggestions (/api/suggest) with settings.
// The whole panel stays hidden if neither API is available.

import { setHeuristicStats, getReference } from "./editor.js";

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

// The last component name in the script, used as heuristic context.
function lastComponent(script) {
  const noComments = script
    .split("\n")
    .map((line) => {
      const hash = line.indexOf("#");
      return hash >= 0 ? line.slice(0, hash) : line;
    })
    .join("\n");
  const noBrackets = noComments.replace(/\[[^\]]*\]?/g, "");
  const matches = [...noBrackets.matchAll(/([A-Za-z_]\w*)/g)]
    .map((m) => m[1])
    .filter((w) => !/^(INPUT|FROM|NEW|CONST|SET|LOOP|TIMES|True|False)$/.test(w));
  return matches.length ? matches[matches.length - 1] : null;
}

// In mid-pipeline context, only segments are valid continuations; when the
// stats fall back to the pipeline-start table (which is source-heavy), drop
// anything the reference identifies as a source.
function filterToSegments(ranked) {
  const ref = getReference();
  if (!ref) return ranked;
  return ranked.filter(([name]) => {
    const comp = ref.byName.get(name);
    return !comp || comp.type !== "source";
  });
}

function renderHeuristics() {
  const list = $("heuristicList");
  list.textContent = "";
  if (!stats) return;

  const script = editor.getValue();
  const prev = lastComponent(script);
  let ranked = [];
  if (prev && stats.bigrams && stats.bigrams[prev]) {
    ranked = Object.entries(stats.bigrams[prev]).sort((a, b) => b[1] - a[1]);
  } else if (stats.starts) {
    ranked = Object.entries(stats.starts).sort((a, b) => b[1] - a[1]);
    if (prev) ranked = filterToSegments(ranked); // mid-pipeline fallback
  }

  if (ranked.length === 0) {
    const empty = document.createElement("div");
    empty.className = "suggest-status";
    empty.textContent = prev
      ? `No history for what follows "${prev}" yet.`
      : "Save some pipelines to build up suggestions.";
    list.appendChild(empty);
    return;
  }

  for (const [name, count] of ranked.slice(0, 8)) {
    const item = document.createElement("div");
    item.className = "suggest-item";
    const badge = document.createElement("span");
    badge.className = "seg-count";
    badge.textContent = `×${count}`;
    badge.title = "How often this follows in saved pipelines and examples";
    const nameSpan = document.createElement("span");
    nameSpan.className = "seg-name";
    nameSpan.textContent = name;
    item.append(badge, nameSpan);
    item.addEventListener("click", () => insertSuggestion(name));
    list.appendChild(item);
  }
}

function insertSuggestion(name, paramsHint) {
  const script = editor.getValue();
  const cursorOffset = editor.getCursorOffset();
  const before = script.slice(0, cursorOffset);
  const needsPipe = /[^|\s]\s*$/.test(before);
  const endsWithSpace = /\s$/.test(before) || !before;
  let prefix = "";
  if (needsPipe) prefix = endsWithSpace ? "| " : " | ";
  else if (before.trim() && !endsWithSpace) prefix = " ";
  const text = prefix + name + (paramsHint ? `[${paramsHint}]` : "");
  editor.insertAtCursor(text);
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
    item.addEventListener("click", () => insertSuggestion(s.segment, s.params_hint));
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
