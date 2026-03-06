/**
 * pixel.dev.js — Development build with verbose logging.
 * DO NOT embed in production. Use dist/pixel.min.js instead.
 */

// Monkey-patch fetch and sendBeacon to log ACK/FAIL
const _fetch = window.fetch;
window.fetch = function (...args) {
  return _fetch(...args).then(res => {
    console.log('[behavioral-pixel] flush ACK', res.status, args[1]?.body?.slice?.(0, 120));
    return res;
  }).catch(err => {
    console.error('[behavioral-pixel] flush FAIL', err);
    throw err;
  });
};

const _sendBeacon = navigator.sendBeacon.bind(navigator);
navigator.sendBeacon = function (url, body) {
  const result = _sendBeacon(url, body);
  console.log('[behavioral-pixel] sendBeacon', result ? 'queued' : 'REJECTED', url);
  return result;
};

// Load the main pixel with verbose config
window.__BEHAVIORAL_CONFIG__ = window.__BEHAVIORAL_CONFIG__ || {};
window.__BEHAVIORAL_CONFIG__.debug = true;

// Import main pixel logic
import './pixel.js';
