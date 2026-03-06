/**
 * pixel.js — Behavioral Intelligence Browser Collector
 * IIFE wrapper prevents global scope pollution.
 * Works in all browsers including WebViews (FBAN, Instagram, WeChat, TikTok).
 */
(function () {
  'use strict';

  // ─── Configuration (injected at embed time) ───────────────────────────────
  const CONFIG = window.__BEHAVIORAL_CONFIG__ || {};
  const INGEST_URL = CONFIG.ingestUrl || '';
  const FLUSH_SIZE = CONFIG.flushSize || 30;
  const FLUSH_INTERVAL_MS = CONFIG.flushIntervalMs || 10_000;

  if (!INGEST_URL) {
    console.warn('[behavioral-pixel] No ingestUrl configured. Events will not be sent.');
    return;
  }

  // ─── Identity ─────────────────────────────────────────────────────────────
  function genId() {
    return crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
  }
  const clientId = (function () {
    try {
      let id = localStorage.getItem('_bx_cid');
      if (!id) { id = genId(); localStorage.setItem('_bx_cid', id); }
      return id;
    } catch (_) { return genId(); }
  })();
  const sessionId = (function () {
    try {
      let id = sessionStorage.getItem('_bx_sid');
      if (!id) { id = genId(); sessionStorage.setItem('_bx_sid', id); }
      return id;
    } catch (_) { return genId(); }
  })();
  let pageId = genId();
  let pageLoadIndex = 1;
  let flushCounter = 0;

  // ─── Buffer ───────────────────────────────────────────────────────────────
  const buffer = [];
  let lastFlushTs = Date.now();
  let lastBeaconTs = 0;
  const DEDUP_MS = 100;

  function push(event) {
    buffer.push(Object.assign({ ts: Date.now(), client_id: clientId, session_id: sessionId, page_id: pageId, page_load_index: pageLoadIndex }, event));
    if (buffer.length >= FLUSH_SIZE) flush('buffer_full');
  }

  function flush(trigger) {
    const now = Date.now();
    if (trigger === 'pagehide' && now - lastBeaconTs < DEDUP_MS) return;
    if (buffer.length === 0) return;
    lastBeaconTs = now;
    flushCounter++;
    const payload = {
      trace_id: sessionId + '_' + flushCounter + '_' + now,
      events: buffer.splice(0),
    };
    send(payload);
    lastFlushTs = now;
  }

  function send(payload) {
    const body = JSON.stringify(payload);
    if (document.visibilityState === 'hidden') {
      navigator.sendBeacon(INGEST_URL, new Blob([body], { type: 'application/json' }));
    } else {
      fetch(INGEST_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {});
    }
  }

  // ─── Interval flush ───────────────────────────────────────────────────────
  setInterval(() => { if (buffer.length > 0) flush('interval'); }, FLUSH_INTERVAL_MS);

  // ─── INIT event ──────────────────────────────────────────────────────────
  push({ event_type: 'INIT', delta_ms: 0, page_path_hash: hashPath(location.pathname) });

  // ─── PAGE_VIEW ────────────────────────────────────────────────────────────
  function onPageView() {
    pageId = genId();
    push({ event_type: 'PAGE_VIEW', delta_ms: 0, page_path_hash: hashPath(location.pathname) });
  }
  window.addEventListener('popstate', () => { pageLoadIndex++; onPageView(); });
  window.addEventListener('hashchange', () => { pageLoadIndex++; onPageView(); });

  // ─── SCROLL ───────────────────────────────────────────────────────────────
  let lastScrollY = window.scrollY, lastScrollTs = Date.now(), lastVelocity = 0, lastScrollDir = 0;
  let rafPending = false;
  window.addEventListener('scroll', () => {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      const now = Date.now();
      const dy = window.scrollY - lastScrollY;
      const dt = Math.max(now - lastScrollTs, 16);
      const velocity = (dy / dt) * 1000;
      const acceleration = (velocity - lastVelocity) / dt * 1000;
      const dir = Math.sign(dy);
      push({
        event_type: 'SCROLL',
        delta_ms: now - lastScrollTs,
        scroll_velocity_px_s: velocity,
        scroll_acceleration: acceleration,
        y_reversal: dir !== 0 && dir !== lastScrollDir && lastScrollDir !== 0 ? 1 : 0,
        scroll_depth_pct: Math.round((window.scrollY / Math.max(document.body.scrollHeight - window.innerHeight, 1)) * 100),
      });
      lastScrollY = window.scrollY;
      lastScrollTs = now;
      lastVelocity = velocity;
      lastScrollDir = dir;
    });
  }, { passive: true });

  // ─── TOUCH_END ────────────────────────────────────────────────────────────
  let lastTouchTs = 0;
  window.addEventListener('touchend', (e) => {
    const now = Date.now();
    const t = e.changedTouches[0];
    push({
      event_type: 'TOUCH_END',
      delta_ms: now - lastTouchTs,
      tap_interval_ms: now - lastTouchTs,
      contact_radius: t ? t.radiusX : 0,
      force: t ? (t.force || 0) : 0,
      dead_tap: t ? (t.radiusX < 2 ? 1 : 0) : 0,
    });
    lastTouchTs = now;
  }, { passive: true });

  // ─── CLICK (non-touch) ───────────────────────────────────────────────────
  let lastClickTs = 0;
  window.addEventListener('click', (e) => {
    if (e.sourceCapabilities && e.sourceCapabilities.firesTouchEvents) return;
    const now = Date.now();
    push({
      event_type: 'CLICK',
      delta_ms: now - lastClickTs,
      tap_interval_ms: now - lastClickTs,
      x: e.clientX,
      y: e.clientY,
    });
    lastClickTs = now;
  });

  // ─── TAB VISIBILITY ───────────────────────────────────────────────────────
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      push({ event_type: 'TAB_HIDDEN', delta_ms: 0 });
      flush('visibilitychange_hidden');
    } else {
      push({ event_type: 'TAB_VISIBLE', delta_ms: 0 });
    }
  });
  window.addEventListener('pagehide', () => flush('pagehide'));

  // ─── Helpers ──────────────────────────────────────────────────────────────
  function hashPath(path) {
    let h = 0;
    for (let i = 0; i < path.length; i++) h = (Math.imul(31, h) + path.charCodeAt(i)) | 0;
    return (h >>> 0).toString(16);
  }

  // ─── Public API ───────────────────────────────────────────────────────────
  window.behavioralPixel = {
    track(eventName, meta = {}) {
      push({ event_type: 'COMMERCIAL', event_name: eventName, delta_ms: 0, ...meta });
      flush('commercial_event');
    },
  };
})();
