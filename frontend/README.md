# Workbench frontend build

This directory exists only to (re)generate the vendored CodeMirror bundle at
`src/talkpipe/app/static/workbench/vendor/codemirror.js`, which is **checked
into git**. End users of talkpipe never need Node.js.

To regenerate (e.g. when upgrading CodeMirror):

```bash
cd frontend
npm ci
npm run build
```

This rebuilds `vendor/codemirror.js` (a single minified ESM bundle) and
`vendor/LICENSES.txt` (aggregated MIT license texts for every bundled
package). Dependency versions are pinned exactly in `package.json` and
`package-lock.json`.

The bundle exports only the symbols re-exported in `src/cm.js`. If the
workbench frontend (`src/talkpipe/app/static/workbench/editor.js`) needs
another CodeMirror API, add it to `src/cm.js` and rebuild.

All application code (editor mode, autocomplete, hover help, lint glue) lives
in `src/talkpipe/app/static/workbench/*.js` as plain ES modules — no build
step, edit and reload.
