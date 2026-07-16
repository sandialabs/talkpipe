// CodeMirror editor setup for the ChatterLang workbench:
// language mode, context-aware autocompletion, hover help, and lint glue.

import {
  EditorState,
  EditorView,
  keymap,
  lineNumbers,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  drawSelection,
  hoverTooltip,
  placeholder,
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
  StreamLanguage,
  syntaxHighlighting,
  defaultHighlightStyle,
  bracketMatching,
  autocompletion,
  completionKeymap,
  closeBrackets,
  closeBracketsKeymap,
  linter,
  lintGutter,
  lintKeymap,
  setDiagnostics,
  searchKeymap,
  highlightSelectionMatches,
  tags,
} from "./vendor/codemirror.js";

// ---------------------------------------------------------------------------
// Reference data (segment/source docs) and heuristic stats, fetched lazily.
// Every consumer tolerates null so the editor works before the API exists
// or while the server-side reference cache is still warming up.

let referencePromise = null;
let referenceData = null; // {byName: Map, sources: [], segments: []}
let heuristicStats = null; // {bigrams: {...}, starts: {...}}

async function fetchReferenceOnce() {
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      const resp = await fetch("/api/reference");
      if (resp.status === 503) {
        // cache still warming
        await new Promise((r) => setTimeout(r, 1500 * (attempt + 1)));
        continue;
      }
      if (!resp.ok) return null;
      const data = await resp.json();
      const byName = new Map();
      const sources = [];
      const segments = [];
      for (const comp of data.components) {
        byName.set(comp.name, comp);
        if (comp.type === "source") sources.push(comp);
        else segments.push(comp);
      }
      return { byName, sources, segments };
    } catch (e) {
      return null;
    }
  }
  return null;
}

export function loadReference() {
  if (!referencePromise) {
    referencePromise = fetchReferenceOnce().then((data) => {
      referenceData = data;
      return data;
    });
  }
  return referencePromise;
}

export function getReference() {
  return referenceData;
}

export function setHeuristicStats(stats) {
  heuristicStats = stats;
}

// ---------------------------------------------------------------------------
// ChatterLang language mode

const KEYWORDS = /^(INPUT|FROM|NEW|CONST|SET|LOOP|TIMES)\b/;

const chatterlangLanguage = StreamLanguage.define({
  name: "chatterlang",
  startState() {
    return { brackets: 0 };
  },
  token(stream, state) {
    if (stream.eatSpace()) return null;
    if (stream.match(/^#.*/)) return "comment";
    if (stream.match(/^"(?:[^"\\]|\\.)*"?/)) return "string";
    if (stream.match(/^'(?:[^'\\]|\\.)*'?/)) return "string";
    if (stream.match(/^-?\d+(\.\d+)?/)) return "number";
    if (stream.match(KEYWORDS)) return "keyword";
    if (stream.match(/^@[A-Za-z_]\w*/)) return "pipeVar";
    if (stream.match(/^\$[A-Za-z_]\w*/)) return "envVar";
    if (stream.match(/^->/)) return "operator";
    if (stream.match(/^[|;]/)) return "operator";
    if (stream.match(/^\[/)) {
      state.brackets++;
      return "bracket";
    }
    if (stream.match(/^\]/)) {
      if (state.brackets > 0) state.brackets--;
      return "bracket";
    }
    if (stream.match(/^[{}(),=]/)) return "punctuation";
    if (stream.match(/^[A-Za-z_]\w*/)) {
      if (state.brackets > 0) {
        // Param name if an `=` follows; otherwise an identifier value.
        return stream.match(/^\s*=/, false) ? "propertyName" : "variableName";
      }
      return "component";
    }
    stream.next();
    return null;
  },
  tokenTable: {
    pipeVar: tags.special(tags.variableName),
    envVar: tags.constant(tags.variableName),
    component: tags.function(tags.variableName),
  },
});

// ---------------------------------------------------------------------------
// Statement context helpers

// Text of the current statement (from the last `;` before pos) up to pos.
function statementBefore(state, pos) {
  const from = Math.max(0, pos - 2000);
  const text = state.sliceDoc(from, pos);
  const semi = text.lastIndexOf(";");
  return semi >= 0 ? text.slice(semi + 1) : text;
}

// Strip comment lines and bracket bodies so structural regexes are reliable.
function structuralText(stmt) {
  return stmt
    .split("\n")
    .map((line) => {
      const hash = line.indexOf("#");
      return hash >= 0 ? line.slice(0, hash) : line;
    })
    .join("\n");
}

function unclosedBracketIndex(text) {
  let depth = 0;
  let idx = -1;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "[") {
      depth++;
      if (depth === 1) idx = i;
    } else if (ch === "]") {
      if (depth > 0) depth--;
      if (depth === 0) idx = -1;
    }
  }
  return depth > 0 ? idx : -1;
}

// The component that precedes the current pipe stage, for heuristic boosts.
function previousComponent(stmt) {
  const noBrackets = stmt.replace(/\[[^\]]*\]?/g, "");
  const stages = noBrackets.split("|");
  if (stages.length < 2) return null;
  const prev = stages[stages.length - 2].trim();
  const m = prev.match(/([A-Za-z_]\w*)\s*$/);
  return m ? m[1] : null;
}

// ---------------------------------------------------------------------------
// Autocompletion

function componentOption(comp, boostMap) {
  const sig = comp.params.map((p) => p.name).join(", ");
  return {
    label: comp.name,
    type: comp.type === "source" ? "class" : "function",
    detail: sig ? `[${sig}]` : undefined,
    info: comp.summary || undefined,
    boost: boostMap && boostMap[comp.name] ? Math.min(99, boostMap[comp.name]) : 0,
  };
}

function paramOptions(comp, stmt) {
  const bracketBody = stmt.slice(stmt.lastIndexOf("[") + 1);
  const used = new Set(
    [...bracketBody.matchAll(/([A-Za-z_]\w*)\s*=/g)].map((m) => m[1])
  );
  return comp.params
    .filter((p) => !used.has(p.name))
    .map((p) => ({
      label: p.name,
      apply: p.name + "=",
      type: "property",
      detail: p.type || undefined,
      info: p.description || (p.default != null ? `default: ${p.default}` : undefined),
    }));
}

function docVariables(state) {
  const vars = new Set();
  for (const m of state.doc.toString().matchAll(/@([A-Za-z_]\w*)/g)) vars.add(m[1]);
  return [...vars].map((v) => ({ label: "@" + v, type: "variable" }));
}

function chatterlangCompletions(context) {
  const ref = referenceData;
  if (!ref) return null;

  const word = context.matchBefore(/[@\w]*/);
  if (word.from === word.to && !context.explicit) return null;

  const stmt = structuralText(statementBefore(context.state, word.from));

  // Inside [...] → param names for the enclosing component.
  const bracketIdx = unclosedBracketIndex(stmt);
  if (bracketIdx >= 0) {
    const before = stmt.slice(0, bracketIdx);
    const nameMatch = before.match(/([A-Za-z_]\w*)\s*$/);
    const comp = nameMatch && ref.byName.get(nameMatch[1]);
    if (!comp) return null;
    return { from: word.from, options: paramOptions(comp, stmt), validFor: /^\w*$/ };
  }

  // After INPUT FROM / NEW → sources (and @variables).
  if (/(?:INPUT\s+FROM|NEW(?:\s+FROM)?)\s+$/i.test(stmt.slice(0, stmt.length))) {
    const options = ref.sources.map((c) => componentOption(c));
    options.push(...docVariables(context.state));
    return { from: word.from, options, validFor: /^[@\w]*$/ };
  }

  // After a pipe → segments, boosted by what tends to follow the previous one.
  if (/\|\s*$/.test(stmt)) {
    const prev = previousComponent(stmt + "x");
    const boostMap =
      heuristicStats && prev && heuristicStats.bigrams
        ? heuristicStats.bigrams[prev]
        : null;
    const options = ref.segments.map((c) => componentOption(c, boostMap));
    options.push(...docVariables(context.state));
    return { from: word.from, options, validFor: /^[@\w]*$/ };
  }

  // Start of a statement → keywords, INPUT FROM snippet, segments.
  if (/^\s*$/.test(stmt)) {
    const options = [
      { label: "INPUT FROM", apply: "INPUT FROM ", type: "keyword" },
      { label: "NEW", apply: "NEW ", type: "keyword" },
      { label: "CONST", apply: "CONST ", type: "keyword" },
      { label: "LOOP", apply: "LOOP 3 TIMES { }", type: "keyword" },
      ...ref.segments.map((c) => componentOption(c)),
    ];
    return { from: word.from, options, validFor: /^[\w]*$/ };
  }

  return null;
}

// ---------------------------------------------------------------------------
// Hover help

function buildHoverDom(comp) {
  const dom = document.createElement("div");
  dom.className = "workbench-hover";
  const title = document.createElement("div");
  const name = document.createElement("span");
  name.className = "hover-name";
  name.textContent = comp.name;
  const type = document.createElement("span");
  type.className = "hover-type";
  type.textContent = comp.type.replace("_", " ");
  title.append(name, type);
  dom.appendChild(title);
  if (comp.error) {
    const err = document.createElement("div");
    err.className = "hover-error";
    err.textContent = `Failed to load: ${comp.error}`;
    dom.appendChild(err);
    return dom;
  }
  if (comp.summary) {
    const summary = document.createElement("div");
    summary.className = "hover-summary";
    summary.textContent = comp.summary;
    dom.appendChild(summary);
  }
  if (comp.params.length) {
    const table = document.createElement("table");
    for (const p of comp.params) {
      const row = table.insertRow();
      const nameCell = row.insertCell();
      nameCell.textContent = p.name + (p.type ? `: ${p.type}` : "");
      const descCell = row.insertCell();
      const bits = [];
      if (p.description) bits.push(p.description);
      if (p.default != null) bits.push(`(default: ${p.default})`);
      descCell.textContent = bits.join(" ");
    }
    dom.appendChild(table);
  }
  return dom;
}

const chatterlangHover = hoverTooltip((view, pos) => {
  const ref = referenceData;
  if (!ref) return null;
  const line = view.state.doc.lineAt(pos);
  const text = line.text;
  const col = pos - line.from;
  let start = col;
  let end = col;
  while (start > 0 && /\w/.test(text[start - 1])) start--;
  while (end < text.length && /\w/.test(text[end])) end++;
  if (start === end) return null;
  const wordText = text.slice(start, end);
  const comp = ref.byName.get(wordText);
  if (!comp) return null;
  return {
    pos: line.from + start,
    end: line.from + end,
    above: false,
    create() {
      return { dom: buildHoverDom(comp) };
    },
  };
});

// ---------------------------------------------------------------------------
// Lint

let lintAvailable = true;

async function lintRequest(script, mode) {
  const resp = await fetch("/api/lint", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ script, mode }),
  });
  if (!resp.ok) throw new Error(`lint failed: ${resp.status}`);
  return (await resp.json()).diagnostics;
}

function toCmDiagnostics(view, diagnostics) {
  const doc = view.state.doc;
  return diagnostics.map((d) => {
    const lineNo = Math.min(Math.max(d.line || 1, 1), doc.lines);
    const line = doc.line(lineNo);
    const from = Math.min(line.from + Math.max((d.column || 1) - 1, 0), line.to);
    let to = from;
    const after = doc.sliceString(from, Math.min(from + 80, line.to));
    const m = after.match(/^\w+/);
    to = m ? from + m[0].length : Math.min(from + 1, line.to);
    return { from, to, severity: d.severity || "error", message: d.message };
  });
}

const chatterlangLinter = linter(
  async (view) => {
    if (!lintAvailable) return [];
    const script = view.state.doc.toString();
    if (!script.trim()) return [];
    try {
      const diagnostics = await lintRequest(script, "parse");
      return toCmDiagnostics(view, diagnostics);
    } catch (e) {
      lintAvailable = false; // endpoint missing/broken: disable quietly
      return [];
    }
  },
  { delay: 600 }
);

// Explicit full-compile check (instantiates components server-side).
export async function runFullCheck(view) {
  const script = view.state.doc.toString();
  if (!script.trim()) return [];
  const diagnostics = await lintRequest(script, "full");
  view.dispatch(setDiagnostics(view.state, toCmDiagnostics(view, diagnostics)));
  return diagnostics;
}

// ---------------------------------------------------------------------------
// Editor construction

export function createEditor(parent, { onCursor, onChange, onRun } = {}) {
  const updateListener = EditorView.updateListener.of((update) => {
    if (update.docChanged && onChange) onChange();
    if ((update.selectionSet || update.docChanged) && onCursor) {
      const head = update.state.selection.main.head;
      const line = update.state.doc.lineAt(head);
      onCursor(line.number, head - line.from + 1);
    }
  });

  const runKey = keymap.of([
    {
      key: "Ctrl-Enter",
      mac: "Cmd-Enter",
      run: () => {
        if (onRun) onRun();
        return true;
      },
    },
  ]);

  const state = EditorState.create({
    doc: "",
    extensions: [
      lineNumbers(),
      highlightActiveLineGutter(),
      highlightSpecialChars(),
      history(),
      drawSelection(),
      EditorState.allowMultipleSelections.of(true),
      bracketMatching(),
      closeBrackets(),
      highlightActiveLine(),
      highlightSelectionMatches(),
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
      chatterlangLanguage,
      autocompletion({ override: [chatterlangCompletions] }),
      chatterlangHover,
      chatterlangLinter,
      lintGutter(),
      placeholder("Enter your ChatterLang script here..."),
      runKey,
      keymap.of([
        ...closeBracketsKeymap,
        ...defaultKeymap,
        ...searchKeymap,
        ...historyKeymap,
        ...completionKeymap,
        ...lintKeymap,
        indentWithTab,
      ]),
      updateListener,
    ],
  });

  const view = new EditorView({ state, parent });
  loadReference();

  return {
    view,
    getValue: () => view.state.doc.toString(),
    setValue: (text) => {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: text },
      });
    },
    insertAtCursor: (text) => {
      const head = view.state.selection.main.head;
      view.dispatch({
        changes: { from: head, insert: text },
        selection: { anchor: head + text.length },
      });
      view.focus();
    },
    getCursorOffset: () => view.state.selection.main.head,
    focus: () => view.focus(),
  };
}
