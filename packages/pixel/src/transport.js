// Transport selection:
// - sendBeacon: when page is unloading (visibilityState === 'hidden') — queued at OS level, fires after page gone
// - fetch keepalive: when page is active — better error handling and response visibility

export function sendPayload(url, payload) {
  const body = JSON.stringify(payload);

  if (document.visibilityState === 'hidden') {
    // Page is unloading — use sendBeacon, it survives tab close
    const sent = navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }));
    if (!sent) {
      // sendBeacon queue full — fall back to keepalive fetch best-effort
      _fetchKeepalive(url, body);
    }
    return;
  }

  _fetchKeepalive(url, body);
}

function _fetchKeepalive(url, body) {
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  }).catch(() => {
    // network failure — payload lost, acceptable tradeoff
  });
}
