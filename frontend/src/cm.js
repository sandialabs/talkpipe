// Re-export surface for the vendored CodeMirror bundle.
// Only symbols listed here are available to the workbench frontend
// (static/workbench/editor.js imports from ./vendor/codemirror.js).

export { EditorState, StateEffect, StateField } from "@codemirror/state";
export {
  EditorView,
  keymap,
  lineNumbers,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  drawSelection,
  rectangularSelection,
  crosshairCursor,
  hoverTooltip,
  placeholder,
} from "@codemirror/view";
export {
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
} from "@codemirror/commands";
export {
  StreamLanguage,
  syntaxHighlighting,
  defaultHighlightStyle,
  HighlightStyle,
  bracketMatching,
  indentUnit,
} from "@codemirror/language";
export {
  autocompletion,
  completionKeymap,
  closeBrackets,
  closeBracketsKeymap,
  acceptCompletion,
  startCompletion,
} from "@codemirror/autocomplete";
export { linter, lintGutter, lintKeymap, setDiagnostics } from "@codemirror/lint";
export { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
export { tags } from "@lezer/highlight";
