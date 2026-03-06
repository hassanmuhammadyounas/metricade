// client_id: localStorage — same device, all tabs, permanent
// session_id: sessionStorage — one tab, one visit, resets on tab close
// page_id: in-memory — one page render, resets on navigation

function generateId() {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function getClientId() {
  let id = localStorage.getItem('_bx_cid');
  if (!id) {
    id = generateId();
    localStorage.setItem('_bx_cid', id);
  }
  return id;
}

export function getSessionId() {
  let id = sessionStorage.getItem('_bx_sid');
  if (!id) {
    id = generateId();
    sessionStorage.setItem('_bx_sid', id);
  }
  return id;
}

export function generatePageId() {
  return generateId();
}
