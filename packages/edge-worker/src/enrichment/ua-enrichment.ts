import { UAParser } from 'ua-parser-js';

export type UaMeta = {
  browser_family: string;
  browser_version: string;
  os_family: string;
  os_version: string;
  device_type: 'desktop' | 'mobile' | 'tablet' | 'bot' | 'unknown';
  device_vendor: string;
  is_webview: boolean;
};

const BOT_RE = /bot|crawl|spider|slurp|googlebot|bingbot/i;

// Patterns that ua-parser-js doesn't classify — reliable server-side webview signals
const WEBVIEW_RE = /FBAN|FBAV|FBIOS|FBSS|Instagram|MicroMessenger|musical_ly|TikTok|Twitter\//;

export function enrichUa(ua: string): UaMeta {
  if (!ua || BOT_RE.test(ua)) {
    return {
      browser_family: 'bot', browser_version: '',
      os_family: 'unknown', os_version: '',
      device_type: 'bot', device_vendor: '',
      is_webview: false,
    };
  }

  const r = new UAParser(ua).getResult();

  const rawType = r.device.type;
  let device_type: UaMeta['device_type'];
  if (rawType === 'mobile') device_type = 'mobile';
  else if (rawType === 'tablet') device_type = 'tablet';
  else if (rawType === undefined) device_type = 'desktop';
  else device_type = 'unknown'; // console, smarttv, wearable, embedded

  const is_webview =
    WEBVIEW_RE.test(ua) ||
    (/Android/.test(ua) && /wv/.test(ua)) ||
    (/iPhone|iPod|iPad/.test(ua) && !/Safari\//.test(ua) && /AppleWebKit/.test(ua));

  return {
    browser_family:  (r.browser.name    ?? 'unknown').toLowerCase(),
    browser_version: (r.browser.version ?? ''),
    os_family:       (r.os.name         ?? 'unknown').toLowerCase(),
    os_version:      (r.os.version      ?? ''),
    device_type,
    device_vendor:   (r.device.vendor   ?? '').toLowerCase(),
    is_webview,
  };
}
