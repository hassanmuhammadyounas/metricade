/**
 * @jest-environment jsdom
 */
import { sendPayload } from '../src/transport.js';

describe('sendPayload', () => {
  const url = 'https://example.com/api/behavioral/ingest';
  const payload = { trace_id: 'abc', events: [] };

  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({ status: 200 });
    global.navigator.sendBeacon = jest.fn().mockReturnValue(true);
  });

  test('uses fetch keepalive when page is visible', () => {
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    sendPayload(url, payload);
    expect(fetch).toHaveBeenCalledWith(url, expect.objectContaining({ keepalive: true }));
    expect(navigator.sendBeacon).not.toHaveBeenCalled();
  });

  test('uses sendBeacon when page is hidden', () => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    sendPayload(url, payload);
    expect(navigator.sendBeacon).toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  test('falls back to fetch keepalive when sendBeacon returns false', () => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    navigator.sendBeacon.mockReturnValue(false);
    sendPayload(url, payload);
    expect(fetch).toHaveBeenCalledWith(url, expect.objectContaining({ keepalive: true }));
  });
});
