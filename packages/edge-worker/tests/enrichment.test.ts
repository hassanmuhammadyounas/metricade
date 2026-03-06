import { describe, it, expect } from 'vitest';
import { enrichUa } from '../src/enrichment/ua-enrichment';
import { encodeTime } from '../src/enrichment/time-encoding';

describe('UA enrichment', () => {
  it('identifies Chrome on Windows as desktop', () => {
    const result = enrichUa('Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/120 Safari/537');
    expect(result.device_type).toBe('desktop');
    expect(result.browser_family).toBe('chrome');
    expect(result.os_family).toBe('windows');
  });

  it('identifies Safari on iPhone as mobile', () => {
    const result = enrichUa('Mozilla/5.0 (iPhone; CPU iPhone OS 15_0) AppleWebKit Mobile Safari/604');
    expect(result.device_type).toBe('mobile');
    expect(result.os_family).toBe('ios');
  });

  it('identifies Googlebot as bot', () => {
    const result = enrichUa('Googlebot/2.1');
    expect(result.device_type).toBe('bot');
  });

  it('detects Facebook WebView', () => {
    const result = enrichUa('Mozilla/5.0 FBAN/FB4A');
    expect(result.is_webview).toBe(true);
    expect(result.webview_type).toBe('facebook');
  });
});

describe('Time encoding', () => {
  it('produces 4 cyclic features', () => {
    const result = encodeTime(Date.now());
    expect(Object.keys(result)).toEqual(['hour_sin', 'hour_cos', 'dow_sin', 'dow_cos']);
  });

  it('all values are in range [-1, 1]', () => {
    const result = encodeTime(Date.now());
    for (const val of Object.values(result)) {
      expect(val).toBeGreaterThanOrEqual(-1);
      expect(val).toBeLessThanOrEqual(1);
    }
  });

  it('midnight and 00:01 have close hour_sin values', () => {
    const midnight = encodeTime(new Date('2024-01-01T00:00:00Z').getTime());
    const oneMin = encodeTime(new Date('2024-01-01T00:01:00Z').getTime());
    expect(Math.abs(midnight.hour_sin - oneMin.hour_sin)).toBeLessThan(0.01);
  });
});
