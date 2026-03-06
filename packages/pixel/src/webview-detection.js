// Detect in-app browsers (WebViews) that may have restricted JS APIs
// Affects: sendBeacon availability, localStorage access, crypto.randomUUID

const UA = navigator.userAgent;

export const isWebView = {
  facebook: /FBAN|FBAV/.test(UA),
  instagram: /Instagram/.test(UA),
  wechat: /MicroMessenger/.test(UA),
  tiktok: /musical_ly|TikTok/.test(UA),
  iosWebView: /iPhone|iPad/.test(UA) && !/Safari/.test(UA) && /AppleWebKit/.test(UA),
  androidWebView: /wv/.test(UA) && /Android/.test(UA),
};

export const isAnyWebView = Object.values(isWebView).some(Boolean);

export function getWebViewType() {
  for (const [type, detected] of Object.entries(isWebView)) {
    if (detected) return type;
  }
  return null;
}
