/**
 * pixel.js — Metricade Pixel
 * IIFE wrapper prevents global scope pollution.
 * Works in all browsers including WebViews (FBAN, Instagram, WeChat, TikTok).
 */
import { AD_CLICK_IDS, UTM_MEDIUM_MAP } from './ad-identifiers.js';
import { getSessionFromReferrer } from './referrer-mapping.js';

(function () {
  'use strict';

  // ─── Configuration ────────────────────────────────────────────────────────
  const config = window.__METRICADE_CONFIG__ || {};
  const ingestUrl    = 'https://worker.metricade.com/ingest';
  const ingestSecret = 'a2714436ee112adcbd0780a68859a76b1522462984ccad0a3e69cdb86b81331b';
  const orgId = config.orgId || null;
  const flushSize = config.flushSize || 30;
  const flushIntervalMs = config.flushIntervalMs || 10_000;
  const debug = !!config.debug;

  if (!orgId) {
    console.error('[metricade-pixel] No orgId configured. Pixel will not run.');
    return;
  }

  // ─── Identity ─────────────────────────────────────────────────────────────
  function genId() {
    return crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36);
  }
  const clientId = (function () {
    try {
      let id = localStorage.getItem('_mtr_cid');
      if (!id) { id = genId(); localStorage.setItem('_mtr_cid', id); }
      return id;
    } catch (_) { return genId(); }
  })();
  const sessionId = (function () {
    try {
      let id = sessionStorage.getItem('_mtr_sid');
      if (!id) { id = genId(); sessionStorage.setItem('_mtr_sid', id); }
      return id;
    } catch (_) { return genId(); }
  })();
  let pageId = genId();
  let pageLoadIndex = 1;
  let flushCounter = (function () { try { return parseInt(sessionStorage.getItem('_mtr_fc') || '0', 10); } catch (_) { return 0; } })();

  // ─── Buffer ───────────────────────────────────────────────────────────────
  const buffer = [];
  let lastBeaconTs = 0;
  const dedupMs = 100;

  function push(event) {
    buffer.push(Object.assign({ ts: Date.now(), page_id: pageId, page_load_index: pageLoadIndex }, event));
    if (buffer.length >= flushSize) flush('buffer_full');
  }

  function flush(trigger) {
    const now = Date.now();
    if (trigger === 'pagehide' && now - lastBeaconTs < dedupMs) return;
    if (buffer.length === 0) return;
    lastBeaconTs = now;
    flushCounter++;
    try { sessionStorage.setItem('_mtr_fc', String(flushCounter)); } catch (_) {}
    const payload = {
      org_id:             orgId,
      client_id:          clientId,
      session_id:         sessionId,
      trace_id:           sessionId + '_' + flushCounter + '_' + now,
      is_touch:           _isTouch ? 1 : 0,
      browser_timezone:   _timezone,
      viewport_w_norm:    Math.round((_vpW / 2560) * 1000) / 1000,
      viewport_h_norm:    Math.round((_vpH / 1440) * 1000) / 1000,
      is_paid:            _isPaid ? 1 : 0,
      session_source:     _sessionSource,
      session_medium:     _sessionMedium,
      device_pixel_ratio: window.devicePixelRatio || 1,
      click_id_type:      _clickIdType,
      events:             buffer.splice(0),
    };
    send(payload);
  }

  function send(payload) {
    if (debug) {
      console.groupCollapsed('[metricade-pixel] flush — ' + payload.events.length + ' event(s) — trace: ' + payload.trace_id.slice(-12));
      payload.events.forEach((ev) => {
        console.log('%c' + ev.event_type, 'font-weight:bold;color:#6366f1', ev);
      });
      console.groupEnd();
      return;
    }
    const body = JSON.stringify(payload);
    const headers = { 'Content-Type': 'application/json' };
    if (ingestSecret) headers['x-ingest-secret'] = ingestSecret;
    if (document.visibilityState === 'hidden') {
      // sendBeacon can't set custom headers — append secret as query param
      const url = ingestSecret ? ingestUrl + (ingestUrl.includes('?') ? '&' : '?') + 's=' + ingestSecret : ingestUrl;
      const sent = navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }));
      if (!sent) {
        // Browser rejected the beacon (queue full) — fall back to keepalive fetch
        fetch(ingestUrl, { method: 'POST', headers, body, keepalive: true }).catch(() => {});
      }
    } else {
      fetch(ingestUrl, { method: 'POST', headers, body, keepalive: true })
        .then((res) => { if (!res.ok) payload.events.forEach((e) => buffer.push(e)); })
        .catch(() => { payload.events.forEach((e) => buffer.push(e)); });
    }
  }

  // ─── Interval flush ───────────────────────────────────────────────────────
  setInterval(() => { if (buffer.length > 0) flush('interval'); }, flushIntervalMs);

  // ─── Session attribution (read once at load) ───────────────────────────────
  // Priority: 1) click ID  2) UTM params  3) document.referrer  4) direct
  const _params = new URLSearchParams(location.search);

  // 1. Click ID
  let _clickIdMatch = null;
  let _clickIdType  = 'none';
  for (const param in AD_CLICK_IDS) {
    if (_params.has(param)) { _clickIdMatch = AD_CLICK_IDS[param]; _clickIdType = param; break; }
  }

  // 2. UTM params
  const _utmMediumRaw = (_params.get('utm_medium') || '').toLowerCase();
  const _utmSource    = _params.get('utm_source') || '';
  const _utmMedium    = UTM_MEDIUM_MAP[_utmMediumRaw] || (_utmMediumRaw || null);

  // 3. Referrer
  const _referrerSession = !_clickIdMatch && !_utmSource ? getSessionFromReferrer(document.referrer) : null;

  // Resolve final session_source / session_medium / is_paid
  let _sessionSource, _sessionMedium, _isPaid;
  if (_clickIdMatch) {
    _sessionSource = _clickIdMatch.platform;
    // paid_only click IDs (gclid, gbraid, wbraid etc.) are exclusively paid —
    // never let UTM override them. Others (fbclid) appear on organic links too,
    // so trust utm_medium when explicitly provided.
    _sessionMedium = _clickIdMatch.paid_only ? _clickIdMatch.medium : (_utmMedium || _clickIdMatch.medium);
    _isPaid        = _clickIdMatch.paid_only ? true : !!(_sessionMedium && _sessionMedium.startsWith('paid'));
  } else if (_utmSource || _utmMedium) {
    _sessionSource = _utmSource || null;
    _sessionMedium = _utmMedium || null;
    _isPaid        = !!(_utmMedium && _utmMedium.startsWith('paid'));
  } else if (_referrerSession) {
    _sessionSource = _referrerSession.session_source;
    _sessionMedium = _referrerSession.session_medium;
    _isPaid        = false;
  } else {
    _sessionSource = 'direct';
    _sessionMedium = 'direct';
    _isPaid        = false;
  }

  // ─── Device context (captured once at load) ───────────────────────────────
  const _isTouch  = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  const _timezone = (function () { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (_) { return ''; } })();
  const _vpW = window.innerWidth;
  const _vpH = window.innerHeight;

  // ─── Cross-browser scroll helpers (spec: section 12) ──────────────────────
  function getScrollY() {
    return window.scrollY !== undefined
      ? window.scrollY
      : (document.documentElement.scrollTop || document.body.scrollTop || 0);
  }
  function getScrollHeight() {
    return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  }

  // ─── Helpers ──────────────────────────────────────────────────────────────
  function hashPath(path) {
    let h = 0x811c9dc5;
    for (let i = 0; i < path.length; i++) {
      h ^= path.charCodeAt(i);
      h = (Math.imul(h, 0x01000193)) >>> 0;
    }
    return h.toString(16).padStart(8, '0');
  }

  function patchX(x) { return Math.round((x / _vpW) * 1000) / 1000; }
  function patchY(y) { return Math.round((y / _vpH) * 1000) / 1000; }

  function isInteractive(el) {
    while (el) {
      const tag = el.tagName;
      if (tag === 'A' || tag === 'BUTTON' || tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || tag === 'LABEL') return true;
      if (el.getAttribute && (el.getAttribute('role') === 'button' || el.getAttribute('onclick') || el.hasAttribute('data-action'))) return true;
      el = el.parentElement;
    }
    return false;
  }

  // ─── init ─────────────────────────────────────────────────────────────────
  push({
    event_type:     'page_view',
    delta_ms:       0,
    page_path_hash: hashPath(location.pathname),
    page_url:       location.href,
  });

  // ─── route_change (SPA navigation only) ──────────────────────────────────
  function onRouteChange() {
    pageId = genId();
    push({ event_type: 'route_change', delta_ms: 0, page_path_hash: hashPath(location.pathname), page_url: location.href });
  }
  window.addEventListener('popstate',   () => { pageLoadIndex++; onRouteChange(); });
  window.addEventListener('hashchange', () => { pageLoadIndex++; onRouteChange(); });

  // ─── scroll ───────────────────────────────────────────────────────────────
  // Attached to BOTH window and document per spec (section 12):
  // some Shopify themes scroll an inner div — only document catches those events.
  let lastScrollY     = getScrollY();
  let lastScrollTs    = Date.now();
  let lastVelocity    = 0;
  let lastScrollDir   = 0;
  let lastScrollEndTs = 0;
  let scrollStopTimer = null;
  let rafPending      = false;

  function onScroll() {
    clearTimeout(scrollStopTimer);
    scrollStopTimer = setTimeout(() => { lastScrollEndTs = Date.now(); }, 150);

    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      const now          = Date.now();
      const scrollY      = getScrollY();
      const dy           = scrollY - lastScrollY;
      const dt           = Math.max(now - lastScrollTs, 16);
      const velocity     = (dy / dt) * 1000;
      const acceleration = (velocity - lastVelocity) / dt * 1000;
      const dir          = Math.sign(dy);
      const pauseDuration = lastScrollEndTs > 0 ? now - lastScrollEndTs : 0;
      const scrollH      = getScrollHeight();

      push({
        event_type:               'scroll',
        delta_ms:                 now - lastScrollTs,
        scroll_velocity_px_s:     Math.round(velocity * 10) / 10,
        scroll_acceleration:      Math.round(acceleration * 10) / 10,
        scroll_direction:         dir,
        y_reversal:               dir !== 0 && dir !== lastScrollDir && lastScrollDir !== 0 ? 1 : 0,
        scroll_depth_pct:         Math.round((scrollY / Math.max(scrollH - window.innerHeight, 1)) * 100),
        scroll_pause_duration_ms: pauseDuration > 500 ? pauseDuration : 0,
        patch_x:                  0,
        patch_y:                  Math.round((scrollY / Math.max(scrollH, 1)) * 1000) / 1000,
      });

      lastScrollEndTs = 0;
      lastScrollY     = scrollY;
      lastScrollTs    = now;
      lastVelocity    = velocity;
      if (dir !== 0) lastScrollDir = dir;
    });
  }

  window.addEventListener('scroll',   onScroll, { passive: true });
  document.addEventListener('scroll', onScroll, { passive: true });

  // ─── touch_end ────────────────────────────────────────────────────────────
  let lastTouchTs  = 0;
  let touchStartTs = 0;
  window.addEventListener('touchstart', () => { touchStartTs = Date.now(); }, { passive: true });
  window.addEventListener('touchend', (e) => {
    const now = Date.now();
    const t   = e.changedTouches[0];
    push({
      event_type:             'touch_end',
      delta_ms:               lastTouchTs > 0 ? now - lastTouchTs : 0,
      tap_interval_ms:        lastTouchTs > 0 ? now - lastTouchTs : 0,
      long_press_duration_ms: touchStartTs > 0 ? now - touchStartTs : 0,
      tap_radius_x:           t ? (t.radiusX || 1) : 1,
      tap_radius_y:           t ? (t.radiusY || 1) : 1,
      tap_pressure:           t ? (t.force   || 0) : 0,
      dead_tap:               t ? (t.radiusX < 2 ? 1 : 0) : 0,
      patch_x:                t ? patchX(t.clientX) : 0,
      patch_y:                t ? patchY(t.clientY) : 0,
    });
    lastTouchTs = now;
  }, { passive: true });

  // ─── click ────────────────────────────────────────────────────────────────
  let lastClickTs = 0;
  window.addEventListener('click', (e) => {
    if (e.sourceCapabilities && e.sourceCapabilities.firesTouchEvents) return;
    const now = Date.now();
    push({
      event_type:      'click',
      delta_ms:        lastClickTs > 0 ? now - lastClickTs : 0,
      tap_interval_ms: lastClickTs > 0 ? now - lastClickTs : 0,
      patch_x:         patchX(e.clientX),
      patch_y:         patchY(e.clientY),
      dead_tap:        isInteractive(e.target) ? 0 : 1,
    });
    lastClickTs = now;
  });

  // ─── tab_hidden / tab_visible ─────────────────────────────────────────────
  let tabHiddenTs = 0;
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      tabHiddenTs = Date.now();
      push({ event_type: 'tab_hidden', delta_ms: 0 });
      flush('visibilitychange_hidden');
    } else {
      push({ event_type: 'tab_visible', delta_ms: 0, backgrounded_ms: tabHiddenTs > 0 ? Date.now() - tabHiddenTs : 0 });
    }
  });
  window.addEventListener('pagehide', () => flush('pagehide'));

  // ─── engagement_tick + idle ───────────────────────────────────────────────
  // engagement_tick fires every 5s while tab is visible and user was active.
  // idle fires once when user has been inactive for >5s (resets on next activity).
  const tickIntervalMs = 5000;
  const idleThresholdMs = 5000;
  let lastActivityTs = Date.now();
  let idleFired = false;

  function onActivity() {
    lastActivityTs = Date.now();
    idleFired = false;
  }

  window.addEventListener('scroll',     onActivity, { passive: true });
  window.addEventListener('click',      onActivity, { passive: true });
  window.addEventListener('touchstart', onActivity, { passive: true });
  window.addEventListener('keydown',    onActivity, { passive: true });

  setInterval(() => {
    if (document.visibilityState === 'hidden') return;
    const now = Date.now();
    const inactiveDuration = now - lastActivityTs;
    if (inactiveDuration >= idleThresholdMs) {
      if (!idleFired) {
        idleFired = true;
        push({ event_type: 'idle', delta_ms: 0, idle_duration_ms: Math.round(inactiveDuration) });
      }
    } else {
      push({ event_type: 'engagement_tick', delta_ms: 0, active_ms: Math.round(now - lastActivityTs) });
    }
  }, tickIntervalMs);


})();
