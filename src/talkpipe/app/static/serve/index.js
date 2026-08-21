/* The / page: submit the form to /process and show the session's history. */
(function () {
  'use strict';

  const { collectFormData, authHeaders, postProcess, errorDetail } = window.TalkpipeServe;

  function showStatus(status, text, kind) {
    status.style.display = 'block';
    status.className = `status ${kind}`;
    status.textContent = text;
  }

  async function submitForm(event) {
    event.preventDefault();
    const form = document.getElementById('dataForm');
    const status = document.getElementById('status');
    const submitBtn = document.getElementById('submitBtn');
    const data = collectFormData(form);

    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitting...';

    try {
      const { response, result } = await postProcess(data);
      if (response.ok) {
        showStatus(status, 'Success: ' + result.message, 'success');
        fetchHistory();
      } else {
        showStatus(status, 'Error: ' + errorDetail(response, result), 'error');
      }
    } catch (error) {
      showStatus(status, 'Error: ' + error.message, 'error');
    }

    submitBtn.disabled = false;
    submitBtn.textContent = 'Submit';

    setTimeout(() => {
      status.style.display = 'none';
    }, 3000);
  }

  async function fetchHistory() {
    try {
      const response = await fetch('/history?limit=10', { headers: authHeaders() });
      const data = await response.json();

      const historyDiv = document.getElementById('history');
      historyDiv.innerHTML = '';
      if (data.entries && data.entries.length > 0) {
        for (const entry of data.entries.reverse()) {
          const item = document.createElement('div');
          item.className = 'history-item';
          item.textContent = JSON.stringify(entry, null, 2);
          historyDiv.appendChild(item);
        }
      } else {
        historyDiv.innerHTML = '<p>No history available</p>';
      }
    } catch (error) {
      console.error('Error fetching history:', error);
    }
  }

  async function clearHistory() {
    try {
      await fetch('/history', { method: 'DELETE', headers: authHeaders() });
      fetchHistory();
    } catch (error) {
      console.error('Error clearing history:', error);
    }
  }

  const form = document.getElementById('dataForm');
  // Enter submits the form (except inside a textarea, where it adds a line).
  form.addEventListener('keypress', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && event.target.tagName !== 'TEXTAREA') {
      event.preventDefault();
      submitForm(event);
    }
  });
  form.addEventListener('submit', submitForm);
  document.getElementById('refreshHistoryBtn').addEventListener('click', fetchHistory);
  document.getElementById('clearHistoryBtn').addEventListener('click', clearHistory);

  fetchHistory();
})();
