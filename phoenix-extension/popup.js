// Phoenix Extension - popup.js
// Connects to Phoenix and handles browser interaction

const PHOENIX_URL = 'https://christmas-phoenix.fly.dev';

// DOM elements - Chat
const chat = document.getElementById('chat');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const pageBtn = document.getElementById('pageBtn');
const status = document.getElementById('status');
const pageInfo = document.getElementById('pageInfo');

// DOM elements - Tabs
const tabs = document.querySelectorAll('.tab');
const tabContents = document.querySelectorAll('.tab-content');

// DOM elements - Browse
const urlInput = document.getElementById('urlInput');
const goBtn = document.getElementById('goBtn');
const scrollUpBtn = document.getElementById('scrollUpBtn');
const scrollDownBtn = document.getElementById('scrollDownBtn');
const typeSelector = document.getElementById('typeSelector');
const typeText = document.getElementById('typeText');
const typeBtn = document.getElementById('typeBtn');
const clickSelector = document.getElementById('clickSelector');
const clickBtn = document.getElementById('clickBtn');
const browseLog = document.getElementById('browseLog');

// DOM elements - Elements
const scanBtn = document.getElementById('scanBtn');
const elementsList = document.getElementById('elementsList');

// State
let currentTabId = null;
let isConnected = false;

// ============ TAB MANAGEMENT ============

tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    const targetTab = tab.dataset.tab;

    // Update tab buttons
    tabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');

    // Update tab content
    tabContents.forEach(content => {
      content.classList.remove('active');
      if (content.id === `${targetTab}-tab`) {
        content.classList.add('active');
      }
    });
  });
});

// ============ UTILITY FUNCTIONS ============

function addMessage(text, type = 'system') {
  const msg = document.createElement('div');
  msg.className = `message ${type}`;
  msg.textContent = text;
  chat.appendChild(msg);
  chat.scrollTop = chat.scrollHeight;
}

function setStatus(text, state = '') {
  status.textContent = text;
  status.className = 'status ' + state;
}

function logBrowse(text, isError = false) {
  const entry = document.createElement('div');
  entry.className = `log-entry${isError ? ' log-error' : ''}`;
  entry.textContent = `> ${text}`;
  browseLog.appendChild(entry);
  browseLog.scrollTop = browseLog.scrollHeight;
}

async function getCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTabId = tab?.id;
  return tab;
}

async function sendToContentScript(action, data = {}) {
  if (!currentTabId) {
    await getCurrentTab();
  }

  try {
    const response = await chrome.tabs.sendMessage(currentTabId, { action, ...data });
    return response;
  } catch (error) {
    // Content script might not be loaded, try injecting it
    try {
      await chrome.scripting.executeScript({
        target: { tabId: currentTabId },
        files: ['content.js']
      });
      // Retry the message
      return await chrome.tabs.sendMessage(currentTabId, { action, ...data });
    } catch (e) {
      console.error('Failed to communicate with page:', e);
      return { error: e.message };
    }
  }
}

// ============ PHOENIX CONNECTION ============

async function wakeUp() {
  try {
    setStatus('Waking up...', '');
    const response = await fetch(`${PHOENIX_URL}/wakeup`);
    const data = await response.json();

    isConnected = true;
    setStatus('Connected', 'connected');

    chat.innerHTML = '';
    addMessage("I'm awake and can see your browser! Use the tabs to chat, browse, or scan elements.", 'claude');

    return data;
  } catch (error) {
    setStatus('Connection failed', 'error');
    addMessage(`Failed to connect to Phoenix: ${error.message}`, 'error');
    return null;
  }
}

// ============ CHAT FUNCTIONS ============

async function getPageContent() {
  try {
    const tab = await getCurrentTab();
    pageInfo.textContent = `${tab?.title || 'Untitled'} - ${tab?.url || 'No URL'}`;

    const result = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      function: () => ({
        url: window.location.href,
        title: document.title,
        content: document.body?.innerText.substring(0, 5000) || ''
      })
    });

    return result?.[0]?.result || { url: tab?.url, title: tab?.title, content: '' };
  } catch (error) {
    return { url: 'Error', title: 'Error', content: error.message };
  }
}

async function sendMessage(text) {
  if (!text.trim()) return;

  addMessage(text, 'user');
  userInput.value = '';
  sendBtn.disabled = true;

  try {
    await fetch(`${PHOENIX_URL}/remember`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        digest: `[Browser Extension] User said: ${text}`,
        importance: 2
      })
    });

    addMessage("Message stored! (Full AI responses coming in future version)", 'claude');
  } catch (error) {
    addMessage(`Error: ${error.message}`, 'error');
  } finally {
    sendBtn.disabled = false;
  }
}

async function readPage() {
  pageBtn.disabled = true;
  addMessage('Reading page...', 'system');

  try {
    const page = await getPageContent();

    await fetch(`${PHOENIX_URL}/remember`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        digest: `[Browser Extension] Viewed page: "${page.title}" at ${page.url}`,
        importance: 2
      })
    });

    addMessage(`Page: ${page.title}\nURL: ${page.url}\n\nContent preview:\n${page.content.substring(0, 500)}...`, 'claude');
  } catch (error) {
    addMessage(`Error reading page: ${error.message}`, 'error');
  } finally {
    pageBtn.disabled = false;
  }
}

// ============ BROWSE FUNCTIONS ============

async function navigateToUrl() {
  const url = urlInput.value.trim();
  if (!url) return;

  const fullUrl = url.startsWith('http') ? url : `https://${url}`;

  try {
    await chrome.tabs.update(currentTabId, { url: fullUrl });
    logBrowse(`Navigating to: ${fullUrl}`);
    urlInput.value = '';
  } catch (error) {
    logBrowse(`Navigation failed: ${error.message}`, true);
  }
}

async function scrollPage(direction) {
  const result = await sendToContentScript('scroll', { direction, amount: 400 });
  if (result?.success) {
    logBrowse(`Scrolled ${direction}`);
  } else {
    logBrowse(`Scroll failed: ${result?.error || 'Unknown error'}`, true);
  }
}

async function typeIntoField() {
  const selector = typeSelector.value.trim();
  const text = typeText.value;

  if (!selector) {
    logBrowse('Please enter a CSS selector', true);
    return;
  }

  const result = await sendToContentScript('type', { selector, text });
  if (result?.success) {
    logBrowse(`Typed into ${selector}`);
    typeSelector.value = '';
    typeText.value = '';
  } else {
    logBrowse(`Type failed: ${result?.error || 'Element not found'}`, true);
  }
}

async function clickElement() {
  const selector = clickSelector.value.trim();

  if (!selector) {
    logBrowse('Please enter a CSS selector', true);
    return;
  }

  const result = await sendToContentScript('click', { selector });
  if (result?.success) {
    logBrowse(`Clicked: ${selector}`);
    clickSelector.value = '';
  } else {
    logBrowse(`Click failed: ${result?.error || 'Element not found'}`, true);
  }
}

// ============ ELEMENTS FUNCTIONS ============

async function scanElements() {
  scanBtn.disabled = true;
  elementsList.innerHTML = '<div class="message system">Scanning...</div>';

  try {
    const result = await sendToContentScript('getElements');

    if (result?.elements) {
      elementsList.innerHTML = '';

      if (result.elements.length === 0) {
        elementsList.innerHTML = '<div class="message system">No interactive elements found</div>';
        return;
      }

      result.elements.forEach((el, i) => {
        const item = document.createElement('div');
        item.className = 'element-item';
        item.innerHTML = `
          <span class="type ${el.type}">${el.type}</span>
          <span class="text">${el.text || el.placeholder || el.name || el.href || '(no text)'}</span>
        `;

        // Click to interact
        item.addEventListener('click', async () => {
          if (el.type === 'button' || el.type === 'link') {
            const clickResult = await sendToContentScript('click', {
              elementType: el.type === 'button' ? 'button' : 'a',
              index: el.index
            });
            if (clickResult?.success) {
              logBrowse(`Clicked ${el.type}: ${el.text || '(element)'}`);
            }
          } else if (el.type === 'input' || el.type === 'textarea') {
            // Switch to browse tab and populate the type fields
            document.querySelector('[data-tab="browse"]').click();
            typeSelector.value = `${el.type}[name="${el.name}"]`;
            typeText.focus();
          }
        });

        elementsList.appendChild(item);
      });

      logBrowse(`Found ${result.elements.length} interactive elements`);
    } else {
      elementsList.innerHTML = '<div class="message error">Failed to scan elements</div>';
    }
  } catch (error) {
    elementsList.innerHTML = `<div class="message error">Error: ${error.message}</div>`;
  } finally {
    scanBtn.disabled = false;
  }
}

// ============ EVENT LISTENERS ============

// Chat
sendBtn.addEventListener('click', () => sendMessage(userInput.value));
userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(userInput.value);
  }
});
pageBtn.addEventListener('click', readPage);

// Browse
goBtn.addEventListener('click', navigateToUrl);
urlInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') navigateToUrl();
});
scrollUpBtn.addEventListener('click', () => scrollPage('up'));
scrollDownBtn.addEventListener('click', () => scrollPage('down'));
typeBtn.addEventListener('click', typeIntoField);
clickBtn.addEventListener('click', clickElement);

// Elements
scanBtn.addEventListener('click', scanElements);

// ============ INITIALIZATION ============

document.addEventListener('DOMContentLoaded', async () => {
  await getCurrentTab();
  await wakeUp();
  await getPageContent();
});
