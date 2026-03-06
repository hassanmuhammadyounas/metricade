/**
 * referrer-mapping.js — Referrer hostname → session_source / session_medium
 *
 * Used as fallback when no click ID or UTM params are present in the URL.
 * Hostname is extracted from document.referrer, www. prefix stripped, then
 * looked up here. If no match, session_source/session_medium remain null.
 *
 * Two lookup strategies:
 *   REFERRER_EXACT   — exact hostname match (social, email, specific engines)
 *   REFERRER_PATTERNS — regex for multi-TLD engines (Google, Bing, Yahoo, etc.)
 *
 * Source: https://github.com/fleetio/dbt-segment/blob/main/seeds/referrer_mapping.csv
 */

export const REFERRER_EXACT = {
  // ── Social ─────────────────────────────────────────────────────────────────
  'facebook.com':       { session_source: 'facebook',   session_medium: 'organic_social' },
  'fb.me':              { session_source: 'facebook',   session_medium: 'organic_social' },
  'm.facebook.com':     { session_source: 'facebook',   session_medium: 'organic_social' },
  'l.facebook.com':     { session_source: 'facebook',   session_medium: 'organic_social' },
  'lm.facebook.com':    { session_source: 'facebook',   session_medium: 'organic_social' },
  'instagram.com':      { session_source: 'instagram',  session_medium: 'organic_social' },
  'twitter.com':        { session_source: 'twitter',    session_medium: 'organic_social' },
  't.co':               { session_source: 'twitter',    session_medium: 'organic_social' },
  'x.com':              { session_source: 'twitter',    session_medium: 'organic_social' },
  'linkedin.com':       { session_source: 'linkedin',   session_medium: 'organic_social' },
  'lnkd.in':            { session_source: 'linkedin',   session_medium: 'organic_social' },
  'youtube.com':        { session_source: 'youtube',    session_medium: 'organic_social' },
  'youtu.be':           { session_source: 'youtube',    session_medium: 'organic_social' },
  'tiktok.com':         { session_source: 'tiktok',     session_medium: 'organic_social' },
  'pinterest.com':      { session_source: 'pinterest',  session_medium: 'organic_social' },
  'pin.it':             { session_source: 'pinterest',  session_medium: 'organic_social' },
  'reddit.com':         { session_source: 'reddit',     session_medium: 'organic_social' },
  'redd.it':            { session_source: 'reddit',     session_medium: 'organic_social' },
  'snapchat.com':       { session_source: 'snapchat',   session_medium: 'organic_social' },
  'threads.net':        { session_source: 'threads',    session_medium: 'organic_social' },
  'weibo.com':          { session_source: 'weibo',      session_medium: 'organic_social' },
  't.cn':               { session_source: 'weibo',      session_medium: 'organic_social' },
  'vk.com':             { session_source: 'vk',         session_medium: 'organic_social' },
  'vkontakte.ru':       { session_source: 'vk',         session_medium: 'organic_social' },
  'tumblr.com':         { session_source: 'tumblr',     session_medium: 'organic_social' },
  'quora.com':          { session_source: 'quora',      session_medium: 'organic_social' },
  'whatsapp.com':       { session_source: 'whatsapp',   session_medium: 'organic_social' },
  'wa.me':              { session_source: 'whatsapp',   session_medium: 'organic_social' },
  'odnoklassniki.ru':   { session_source: 'ok',         session_medium: 'organic_social' },
  'ok.ru':              { session_source: 'ok',         session_medium: 'organic_social' },

  // ── Email ──────────────────────────────────────────────────────────────────
  'mail.google.com':    { session_source: 'gmail',        session_medium: 'email' },
  'mail.yahoo.com':     { session_source: 'yahoo_mail',   session_medium: 'email' },
  'mail.yahoo.co.uk':   { session_source: 'yahoo_mail',   session_medium: 'email' },
  'mail.yahoo.co.jp':   { session_source: 'yahoo_mail',   session_medium: 'email' },
  'mail.live.com':      { session_source: 'outlook',      session_medium: 'email' },
  'outlook.live.com':   { session_source: 'outlook',      session_medium: 'email' },
  'outlook.office.com': { session_source: 'outlook',      session_medium: 'email' },
  'mail.aol.com':       { session_source: 'aol_mail',     session_medium: 'email' },
  'mail.qq.com':        { session_source: 'qq_mail',      session_medium: 'email' },
  'mail.126.com':       { session_source: '126_mail',     session_medium: 'email' },
  'mail.163.com':       { session_source: '163_mail',     session_medium: 'email' },
  'mail.naver.com':     { session_source: 'naver_mail',   session_medium: 'email' },

  // ── Search (single-TLD) ────────────────────────────────────────────────────
  'duckduckgo.com':     { session_source: 'duckduckgo',  session_medium: 'organic_search' },
  'ecosia.org':         { session_source: 'ecosia',      session_medium: 'organic_search' },
  'startpage.com':      { session_source: 'startpage',   session_medium: 'organic_search' },
  'ask.com':            { session_source: 'ask',         session_medium: 'organic_search' },
  'naver.com':          { session_source: 'naver',       session_medium: 'organic_search' },
};

/**
 * Pattern-based matching for search engines with many TLDs.
 * Checked in order — first match wins.
 */
export const REFERRER_PATTERNS = [
  { test: (h) => /\.?google\./.test(h),  session_source: 'google',  session_medium: 'organic_search' },
  { test: (h) => /\.?bing\./.test(h),    session_source: 'bing',    session_medium: 'organic_search' },
  { test: (h) => /\.?yahoo\./.test(h),   session_source: 'yahoo',   session_medium: 'organic_search' },
  { test: (h) => /\.?yandex\./.test(h),  session_source: 'yandex',  session_medium: 'organic_search' },
  { test: (h) => /\.?baidu\./.test(h),   session_source: 'baidu',   session_medium: 'organic_search' },
  { test: (h) => /\.?seznam\./.test(h),  session_source: 'seznam',  session_medium: 'organic_search' },
];

export function getSessionFromReferrer(referrerUrl) {
  if (!referrerUrl) return null;
  try {
    const host = new URL(referrerUrl).hostname.replace(/^www\./, '');
    if (REFERRER_EXACT[host]) return REFERRER_EXACT[host];
    for (const rule of REFERRER_PATTERNS) {
      if (rule.test(host)) return { session_source: rule.session_source, session_medium: rule.session_medium };
    }
    return null;
  } catch (_) { return null; }
}
