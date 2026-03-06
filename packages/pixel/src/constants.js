// Event type enums
export const EVENT_TYPES = {
  INIT: 'INIT',
  PAGE_VIEW: 'PAGE_VIEW',
  SCROLL: 'SCROLL',
  TOUCH_END: 'TOUCH_END',
  CLICK: 'CLICK',
  TAB_HIDDEN: 'TAB_HIDDEN',
  TAB_VISIBLE: 'TAB_VISIBLE',
};

// Flush trigger conditions
export const FLUSH_TRIGGERS = {
  BUFFER_SIZE: 30,        // flush after 30 events accumulated
  INTERVAL_MS: 10_000,    // flush every 10 seconds
  VISIBILITY_HIDDEN: 'visibilitychange_hidden',
  PAGEHIDE: 'pagehide',
};

export const DEDUP_GUARD_MS = 100; // prevent double-flush on pagehide + visibilitychange
