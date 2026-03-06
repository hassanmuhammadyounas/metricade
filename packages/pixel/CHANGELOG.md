# pixel.js Changelog

## v1.0.0 — Initial Release
- INIT, PAGE_VIEW, SCROLL, TOUCH_END, CLICK, TAB_HIDDEN, TAB_VISIBLE event capture
- 30-event buffer flush, 10-second interval flush
- sendBeacon on unload, fetch keepalive when active
- 100ms dedup guard on pagehide + visibilitychange
- client_id (localStorage), session_id (sessionStorage), page_id (in-memory)
- SPA support via popstate + hashchange
- WebView detection (FBAN, Instagram, WeChat, TikTok, iOS, Android)
- window.behavioralPixel.track() public API for commercial events
