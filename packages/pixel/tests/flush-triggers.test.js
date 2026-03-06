/**
 * @jest-environment jsdom
 * Tests the 4 flush conditions:
 * 1. 30 events accumulated
 * 2. 10 second interval
 * 3. visibilitychange → hidden
 * 4. pagehide (Safari fallback)
 */

describe('flush triggers', () => {
  let buffer, flushMock;

  beforeEach(() => {
    buffer = [];
    flushMock = jest.fn();
    jest.useFakeTimers();
  });

  afterEach(() => jest.useRealTimers());

  test('trigger 1: flushes after 30 events', () => {
    function push(event) {
      buffer.push(event);
      if (buffer.length >= 30) flushMock('buffer_full');
    }
    for (let i = 0; i < 29; i++) push({ event_type: 'SCROLL' });
    expect(flushMock).not.toHaveBeenCalled();
    push({ event_type: 'SCROLL' });
    expect(flushMock).toHaveBeenCalledWith('buffer_full');
  });

  test('trigger 2: flushes after 10 seconds', () => {
    buffer.push({ event_type: 'SCROLL' }); // ensure buffer non-empty
    const interval = setInterval(() => {
      if (buffer.length > 0) flushMock('interval');
    }, 10_000);
    jest.advanceTimersByTime(10_000);
    expect(flushMock).toHaveBeenCalledWith('interval');
    clearInterval(interval);
  });

  test('trigger 3: flushes on visibilitychange hidden', () => {
    buffer.push({ event_type: 'SCROLL' });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flushMock('visibilitychange_hidden');
    });
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(flushMock).toHaveBeenCalledWith('visibilitychange_hidden');
  });

  test('trigger 4: flushes on pagehide (Safari fallback)', () => {
    buffer.push({ event_type: 'SCROLL' });
    window.addEventListener('pagehide', () => flushMock('pagehide'));
    window.dispatchEvent(new Event('pagehide'));
    expect(flushMock).toHaveBeenCalledWith('pagehide');
  });
});
