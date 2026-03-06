export type UaMeta = {
  browser_family: string;
  os_family: string;
  device_type: 'desktop' | 'mobile' | 'tablet' | 'bot' | 'unknown';
  is_webview: boolean;
  webview_type: string | null;
};

const WEBVIEW_PATTERNS: Array<[string, RegExp]> = [
  ['facebook', /FBAN|FBAV/],
  ['instagram', /Instagram/],
  ['wechat', /MicroMessenger/],
  ['tiktok', /musical_ly|TikTok/],
];

export function enrichUa(ua: string): UaMeta {
  const isBot = /bot|crawl|spider|slurp|googlebot|bingbot/i.test(ua);
  const isMobile = /Mobile|Android|iPhone|iPad/i.test(ua);
  const isTablet = /iPad|Tablet/i.test(ua);

  let webviewType: string | null = null;
  for (const [type, pattern] of WEBVIEW_PATTERNS) {
    if (pattern.test(ua)) { webviewType = type; break; }
  }

  return {
    browser_family: parseBrowserFamily(ua),
    os_family: parseOsFamily(ua),
    device_type: isBot ? 'bot' : isTablet ? 'tablet' : isMobile ? 'mobile' : 'desktop',
    is_webview: webviewType !== null,
    webview_type: webviewType,
  };
}

function parseBrowserFamily(ua: string): string {
  if (/Chrome/.test(ua) && !/Chromium|Edge/.test(ua)) return 'chrome';
  if (/Firefox/.test(ua)) return 'firefox';
  if (/Safari/.test(ua) && !/Chrome/.test(ua)) return 'safari';
  if (/Edge/.test(ua)) return 'edge';
  return 'other';
}

function parseOsFamily(ua: string): string {
  if (/Windows/.test(ua)) return 'windows';
  if (/Mac OS X/.test(ua) && !/iPhone|iPad/.test(ua)) return 'macos';
  if (/iPhone|iPad/.test(ua)) return 'ios';
  if (/Android/.test(ua)) return 'android';
  if (/Linux/.test(ua)) return 'linux';
  return 'other';
}
