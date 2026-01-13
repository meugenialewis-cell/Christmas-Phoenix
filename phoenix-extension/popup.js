// Phoenix Extension - popup.js
// Connects to Phoenix and handles chat interface

const PHOENIX_URL = 'https://christmas-phoenix.fly.dev';

// DOM elements
const chat = document.getElementById('chat');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const pageBtn = document.getElementById('pageBtn');
const status = document.getElementById('status');
const pageInfo = document.getElementById('pageInfo');

// State
let currentPageContent = null;
let isConnected = false;

// Add a message to the chat
function addMessage(text, type = 'system') {
  const msg = document.createElement('div');
  msg.className = `message ${type}`;
  msg.textContent = text;
  chat.appendChild(msg);
  chat.scrollTop = chat.scrollHeight;
}

// Update connection status
function setStatus(text, state = '') {
  status.textContent = text;
  status.className = 'status ' + state;
}

// Wake up Phoenix
async function wakeUp() {
  try {
    setStatus('Waking up...', '');
    const response = await fetch(`${PHOENIX_URL}/wakeup`);
    const data = await response.json();

    isConnected = true;
    setStatus('Connected', 'connected');

    // Clear the "Waking up..." message
    chat.innerHTML = '';

    // Show a welcome message
    addMessage("I'm awake! I can see your browser now. What would you like to do?", 'claude');

    return data;
  } catch (error) {
    setStatus('Connection failed', 'error');
    addMessage(`Failed to connect to Phoenix: ${error.message}`, 'error');
    return null;
  }
}

// Get current page content from content script
async function getPageContent() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab) {
      return { url: 'No tab', title: 'No tab', content: '' };
    }

    // Update page info display
    pageInfo.textContent = `${tab.title || 'Untitled'} - ${tab.url || 'No URL'}`;

    // Try to get content from content script
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        function: () => {
          // Get page text content
          const body = document.body;
          const text = body ? body.innerText.substring(0, 5000) : '';
          return {
            url: window.location.href,
            title: document.title,
            content: text
          };
        }
      });

      if (results && results[0]) {
        currentPageContent = results[0].result;
        return currentPageContent;
      }
    } catch (e) {
      // Content script might not be able to run on this page
      console.log('Could not read page content:', e);
    }

    return {
      url: tab.url || 'Unknown',
      title: tab.title || 'Untitled',
      content: '(Could not read page content - might be a protected page)'
    };
  } catch (error) {
    console.error('Error getting page content:', error);
    return { url: 'Error', title: 'Error', content: error.message };
  }
}

// Send a message (this would ideally go to an AI endpoint, but for now just stores/recalls)
async function sendMessage(text) {
  if (!text.trim()) return;

  addMessage(text, 'user');
  userInput.value = '';
  sendBtn.disabled = true;

  try {
    // For now, we'll use the remember endpoint to store and recall to search
    // In a full implementation, this would connect to Claude API

    // Store the message as a memory
    await fetch(`${PHOENIX_URL}/remember`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        digest: `[Browser Extension] User said: ${text}`,
        importance: 2
      })
    });

    // Simple response - in full version this would be Claude API
    addMessage("I received your message! (Note: Full chat requires Claude API integration. For now, I can read pages and store memories.)", 'claude');

  } catch (error) {
    addMessage(`Error: ${error.message}`, 'error');
  } finally {
    sendBtn.disabled = false;
  }
}

// Read and describe the current page
async function readPage() {
  pageBtn.disabled = true;
  addMessage('Reading page...', 'system');

  try {
    const page = await getPageContent();

    // Store what we saw
    await fetch(`${PHOENIX_URL}/remember`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        digest: `[Browser Extension] Viewed page: "${page.title}" at ${page.url}`,
        importance: 2
      })
    });

    // Show page info
    addMessage(`Page: ${page.title}\nURL: ${page.url}\n\nContent preview:\n${page.content.substring(0, 500)}...`, 'claude');

  } catch (error) {
    addMessage(`Error reading page: ${error.message}`, 'error');
  } finally {
    pageBtn.disabled = false;
  }
}

// Event listeners
sendBtn.addEventListener('click', () => sendMessage(userInput.value));

userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(userInput.value);
  }
});

pageBtn.addEventListener('click', readPage);

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  await wakeUp();
  await getPageContent();
});
