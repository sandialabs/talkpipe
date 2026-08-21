/* The /stream page: a chat-style view of a ChatterLang pipeline. Results are
 * displayed from the /process response; the SSE stream carries errors. */
(function () {
  'use strict';

  const { collectFormData, postProcess, errorDetail } = window.TalkpipeServe;

  let autoScroll = true;
  let lastUserMessage = null; // Track last user message to avoid duplicates
  let pendingRequest = false; // True while /process request is in flight
  let sseBuffer = []; // Buffer SSE events during request to avoid duplicate display

  // Markdown -> sanitised HTML. marked and DOMPurify are served from
  // /static/serve/vendor/; if either is missing the text is shown as-is.
  function renderMarkdown(text) {
    if (typeof text !== 'string' || text === '') return '';
    try {
      const parseFn = (typeof marked !== 'undefined' && marked.parse) ? marked.parse
        : (typeof marked === 'function') ? marked : null;
      const raw = parseFn ? parseFn(text, { breaks: true }) : text;
      return (typeof DOMPurify !== 'undefined' && DOMPurify.sanitize) ? DOMPurify.sanitize(raw) : raw;
    } catch (e) {
      return text;
    }
  }

  function setConnectionStatus(text, color) {
    const status = document.getElementById('connectionStatus');
    status.textContent = text;
    status.style.color = color;
  }

  function initSSE() {
    const eventSource = new EventSource('/output-stream');
    eventSource.onopen = function () {
      setConnectionStatus('Connected', 'green');
    };
    eventSource.onmessage = function (event) {
      try {
        const data = JSON.parse(event.data);
        // Skip user messages from server since we display them immediately on client
        if (data.type === 'user' && data.output === lastUserMessage) {
          return;
        }
        // Buffer SSE during /process request - we'll display from response to avoid duplicates
        if (pendingRequest && data.type === 'response') {
          sseBuffer.push(data);
          return;
        }
        addMessage(data.output, data.type || 'response', data.timestamp);
      } catch (e) {
        console.error('Error parsing SSE data:', e);
      }
    };
    eventSource.onerror = function () {
      setConnectionStatus('Connection error', 'red');
    };
  }

  // Clear the form, but keep fields marked data-persist.
  function resetFormSelectively(form) {
    form.querySelectorAll('input, select, textarea').forEach((element) => {
      if (element.hasAttribute('data-persist')) return;
      if (element.type === 'checkbox' || element.type === 'radio') {
        element.checked = false;
      } else {
        element.value = '';
      }
    });
  }

  function flashCopied(button) {
    const originalContent = button.innerHTML;
    button.innerHTML = '✓';
    button.classList.add('copied');
    setTimeout(() => {
      button.innerHTML = originalContent;
      button.classList.remove('copied');
    }, 2000);
  }

  function copyToClipboard(text, button) {
    navigator.clipboard.writeText(text).then(() => flashCopied(button)).catch((err) => {
      console.error('Failed to copy text: ', err);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        flashCopied(button);
      } catch (err2) {
        console.error('Fallback copy failed: ', err2);
      }
      document.body.removeChild(textArea);
    });
  }

  function addMessage(content, type, timestamp) {
    const messagesContainer = document.getElementById('chatMessages');
    const initialMessage = messagesContainer.querySelector('.initial-message');
    if (initialMessage) {
      initialMessage.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;

    const timestampDiv = document.createElement('div');
    timestampDiv.className = 'message-timestamp';
    timestampDiv.textContent = new Date(timestamp).toLocaleTimeString();

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    if (type === 'response' || type === 'error') {
      contentDiv.innerHTML = renderMarkdown(content);
    } else {
      contentDiv.textContent = content;
    }

    messageDiv.appendChild(timestampDiv);
    messageDiv.appendChild(contentDiv);

    if (type === 'response' || type === 'error') {
      const copyBtn = document.createElement('button');
      copyBtn.className = 'copy-btn';
      copyBtn.innerHTML = '📋';
      copyBtn.title = 'Copy message';
      copyBtn.addEventListener('click', () => copyToClipboard(content, copyBtn));
      messageDiv.appendChild(copyBtn);
    }
    messagesContainer.appendChild(messageDiv);

    if (autoScroll) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
  }

  function clearChat() {
    document.getElementById('chatMessages').innerHTML =
      '<div class="initial-message">Chat cleared. Send a message to continue.</div>';
  }

  function toggleAutoScroll() {
    autoScroll = !autoScroll;
    document.getElementById('autoScrollBtn').textContent = `Auto-scroll: ${autoScroll ? 'ON' : 'OFF'}`;
  }

  function showStatus(status, text, kind) {
    status.textContent = text;
    status.className = `status ${kind}`;
    status.style.display = 'block';
  }

  async function submitForm(event) {
    event.preventDefault();
    const form = document.getElementById('dataForm');
    const status = document.getElementById('status');
    const submitBtn = document.getElementById('submitBtn');
    const data = collectFormData(form);

    // Show the user's message immediately; --display-property picks the field.
    const displayProperty = form.dataset.displayProperty || Object.keys(data)[0];
    const userMessage = data[displayProperty] || JSON.stringify(data);
    lastUserMessage = userMessage; // Store to detect duplicates from server
    addMessage(userMessage, 'user', new Date().toISOString());

    resetFormSelectively(form);

    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending...';
    pendingRequest = true;
    sseBuffer = [];

    try {
      const { response, result } = await postProcess(data);
      if (!response.ok) {
        throw new Error(errorDetail(response, result));
      }

      showStatus(status, 'Message sent successfully!', 'success');

      // Display results from response - more reliable than SSE for batch results
      // (avoids race where SSE may not deliver all items before next interaction)
      if (result.data && result.data.output && Array.isArray(result.data.output)) {
        const timestamp = result.timestamp || new Date().toISOString();
        for (const item of result.data.output) {
          const content = typeof item === 'object' ? JSON.stringify(item, null, 2) : String(item);
          addMessage(content, 'response', timestamp);
        }
      }
      sseBuffer = []; // Discard buffered SSE - we displayed from response

      setTimeout(() => {
        status.style.display = 'none';
        lastUserMessage = null; // Clear after a delay
      }, 3000);
    } catch (error) {
      showStatus(status, `Error: ${error.message}`, 'error');
      addMessage(`Error: ${error.message}`, 'error', new Date().toISOString());
      lastUserMessage = null; // Clear on error
      sseBuffer = [];
    } finally {
      pendingRequest = false;
      submitBtn.disabled = false;
      submitBtn.textContent = 'Send Message';
    }
  }

  document.getElementById('dataForm').addEventListener('submit', submitForm);
  document.getElementById('clearChatBtn').addEventListener('click', clearChat);
  document.getElementById('autoScrollBtn').addEventListener('click', toggleAutoScroll);
  initSSE();
})();
