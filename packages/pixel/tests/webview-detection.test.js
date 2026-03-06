/**
 * @jest-environment jsdom
 */

function detectWebView(ua) {
  return {
    facebook: /FBAN|FBAV/.test(ua),
    instagram: /Instagram/.test(ua),
    wechat: /MicroMessenger/.test(ua),
    tiktok: /musical_ly|TikTok/.test(ua),
    iosWebView: /iPhone|iPad/.test(ua) && !/Safari/.test(ua) && /AppleWebKit/.test(ua),
    androidWebView: /wv/.test(ua) && /Android/.test(ua),
  };
}

describe('WebView detection', () => {
  test('detects Facebook in-app browser', () => {
    expect(detectWebView('Mozilla/5.0 FBAN/FB4A')).toMatchObject({ facebook: true });
  });

  test('detects Instagram WebView', () => {
    expect(detectWebView('Mozilla/5.0 Instagram 123')).toMatchObject({ instagram: true });
  });

  test('detects WeChat', () => {
    expect(detectWebView('MicroMessenger/7.0')).toMatchObject({ wechat: true });
  });

  test('detects TikTok', () => {
    expect(detectWebView('musical_ly/1.0')).toMatchObject({ tiktok: true });
  });

  test('detects iOS WebView (no Safari)', () => {
    const ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0) AppleWebKit/605.1';
    expect(detectWebView(ua)).toMatchObject({ iosWebView: true });
  });

  test('does NOT flag regular Safari as WebView', () => {
    const ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0) AppleWebKit/605.1 Safari/604.1';
    expect(detectWebView(ua)).toMatchObject({ iosWebView: false });
  });

  test('detects Android WebView', () => {
    expect(detectWebView('Mozilla/5.0 (Linux; Android 11; wv) AppleWebKit')).toMatchObject({ androidWebView: true });
  });

  test('clean Chrome UA returns all false', () => {
    const ua = 'Mozilla/5.0 (Windows NT 10.0) Chrome/120.0.0.0 Safari/537.36';
    const result = detectWebView(ua);
    expect(Object.values(result).every(v => v === false)).toBe(true);
  });
});
