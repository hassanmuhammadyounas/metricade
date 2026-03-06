# pixel.js — Browser Behavioral Collector

Vanilla JavaScript browser collector. No dependencies. Works in all browsers including WebViews (Facebook, Instagram, WeChat, TikTok).

## Embedding

```html
<script>
  window.__BEHAVIORAL_CONFIG__ = {
    ingestUrl: 'https://your-domain.com/api/behavioral/ingest',
  };
</script>
<script src="https://your-cdn.com/pixel.min.js" async></script>
```

## Events Collected

| Event | Description |
|---|---|
| `INIT` | Script load baseline — device, browser, timezone |
| `PAGE_VIEW` | Page load and SPA navigation |
| `SCROLL` | Scroll physics — velocity, acceleration, reversal, depth |
| `TOUCH_END` | Touch tap — interval, radius, force, dead_tap |
| `CLICK` | Click position and interval (non-touch only) |
| `TAB_HIDDEN` | Tab backgrounded — triggers immediate flush |
| `TAB_VISIBLE` | Tab returned to foreground |

## Configuration Options

| Option | Default | Description |
|---|---|---|
| `ingestUrl` | `''` | Required. Worker ingestion URL |
| `flushSize` | `30` | Events before forced flush |
| `flushIntervalMs` | `10000` | Max ms between flushes |

## Public API

```js
window.behavioralPixel.track('add_to_cart', { value: 49.99 });
```

## Build

```bash
npm run build      # production minified → dist/pixel.min.js
npm run build:dev  # development verbose → dist/pixel.dev.js
npm test           # run all tests
```
