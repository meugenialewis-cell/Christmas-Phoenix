// Phoenix Extension - content.js
// Runs on every page - can read and interact with page content

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getPageContent') {
    const content = {
      url: window.location.href,
      title: document.title,
      content: document.body ? document.body.innerText.substring(0, 10000) : '',
      html: document.body ? document.body.innerHTML.substring(0, 20000) : ''
    };
    sendResponse(content);
  }

  if (request.action === 'getElements') {
    // Find interactive elements
    const elements = [];

    // Buttons
    document.querySelectorAll('button').forEach((el, i) => {
      elements.push({
        type: 'button',
        text: el.textContent.trim().substring(0, 50),
        index: i
      });
    });

    // Links
    document.querySelectorAll('a').forEach((el, i) => {
      elements.push({
        type: 'link',
        text: el.textContent.trim().substring(0, 50),
        href: el.href,
        index: i
      });
    });

    // Input fields
    document.querySelectorAll('input, textarea').forEach((el, i) => {
      elements.push({
        type: el.tagName.toLowerCase(),
        name: el.name || el.id || `input-${i}`,
        placeholder: el.placeholder || '',
        index: i
      });
    });

    sendResponse({ elements: elements.slice(0, 100) }); // Limit to 100 elements
  }

  if (request.action === 'click') {
    // Click an element by selector or index
    const { selector, elementType, index } = request;

    let element;
    if (selector) {
      element = document.querySelector(selector);
    } else if (elementType && index !== undefined) {
      const elements = document.querySelectorAll(elementType);
      element = elements[index];
    }

    if (element) {
      element.click();
      sendResponse({ success: true });
    } else {
      sendResponse({ success: false, error: 'Element not found' });
    }
  }

  if (request.action === 'type') {
    // Type into an input field
    const { selector, text } = request;
    const element = document.querySelector(selector);

    if (element && (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA')) {
      element.value = text;
      element.dispatchEvent(new Event('input', { bubbles: true }));
      sendResponse({ success: true });
    } else {
      sendResponse({ success: false, error: 'Input element not found' });
    }
  }

  if (request.action === 'scroll') {
    // Scroll the page
    const { direction, amount } = request;
    if (direction === 'down') {
      window.scrollBy(0, amount || 500);
    } else if (direction === 'up') {
      window.scrollBy(0, -(amount || 500));
    }
    sendResponse({ success: true });
  }

  // Required for async response
  return true;
});

// Announce that content script is loaded
console.log('Phoenix content script loaded');
