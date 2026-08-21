/* Shared by the chatterlang_serve pages (/ and /stream): read the form as
 * JSON, attach the API key, and POST to /process. */
(function (global) {
  'use strict';

  // Build the JSON payload from the form. The API key field is never part of
  // the payload; numbers are parsed and checkboxes sent as booleans.
  function collectFormData(form) {
    const data = {};
    for (const [key, value] of new FormData(form).entries()) {
      if (key === 'apiKey') continue;
      const input = form.elements[key];
      if (input.type === 'number') {
        data[key] = value ? parseFloat(value) : null;
      } else if (input.type === 'checkbox') {
        data[key] = input.checked;
      } else {
        data[key] = value;
      }
    }
    return data;
  }

  // Request headers, with X-API-Key when the page has an API key field
  // (the server only renders one when authentication is required).
  function authHeaders(headers) {
    const result = Object.assign({}, headers || {});
    const apiKey = document.getElementById('apiKey');
    if (apiKey && apiKey.value) {
      result['X-API-Key'] = apiKey.value;
    }
    return result;
  }

  async function postProcess(data) {
    const response = await fetch('/process', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(data),
    });
    const result = await response.json();
    return { response, result };
  }

  // A readable message for a failed /process call.
  function errorDetail(response, result) {
    const detail = result && result.detail;
    if (typeof detail === 'string') return detail;
    if (detail) return JSON.stringify(detail);
    return `HTTP ${response.status}: ${response.statusText}`;
  }

  global.TalkpipeServe = { collectFormData, authHeaders, postProcess, errorDetail };
})(window);
