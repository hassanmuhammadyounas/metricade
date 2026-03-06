/**
 * @jest-environment jsdom
 */
import { getClientId, getSessionId, generatePageId } from '../src/identity.js';

describe('client_id', () => {
  beforeEach(() => localStorage.clear());

  test('generates and persists client_id in localStorage', () => {
    const id1 = getClientId();
    const id2 = getClientId();
    expect(id1).toBe(id2);
    expect(localStorage.getItem('_bx_cid')).toBe(id1);
  });

  test('generates unique ids across fresh localStorage', () => {
    const id1 = getClientId();
    localStorage.clear();
    const id2 = getClientId();
    expect(id1).not.toBe(id2);
  });
});

describe('session_id', () => {
  beforeEach(() => sessionStorage.clear());

  test('generates and persists session_id in sessionStorage', () => {
    const id1 = getSessionId();
    const id2 = getSessionId();
    expect(id1).toBe(id2);
    expect(sessionStorage.getItem('_bx_sid')).toBe(id1);
  });

  test('sessionStorage isolation: different session IDs per tab (simulated)', () => {
    const id1 = getSessionId();
    sessionStorage.clear();
    const id2 = getSessionId();
    expect(id1).not.toBe(id2);
  });
});

describe('page_id', () => {
  test('generates unique page_id on each call', () => {
    const id1 = generatePageId();
    const id2 = generatePageId();
    expect(id1).not.toBe(id2);
  });
});
