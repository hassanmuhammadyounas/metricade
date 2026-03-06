/**
 * ad-identifiers.js — Global ad click ID and UTM medium mapping
 *
 * AD_CLICK_IDS
 *   Maps URL parameter names to { platform, medium }.
 *   Add new entries here as platforms introduce new click IDs.
 *   Sources:
 *     - https://www.appfromlab.com/posts/list-of-click-identifiers/
 *     - https://en.wikipedia.org/wiki/Click_identifier
 *     - https://businesshelp.snapchat.com/s/article/url-parameters
 *     - https://help.pinterest.com/en/business/article/pinterest-tag-parameters-and-cookies
 *     - https://www.utmguard.com/docs/platform-conflicts/rdt-cid-utm-conflict
 *
 * UTM_MEDIUM_MAP
 *   Normalizes raw utm_medium values to a canonical channel bucket.
 *   Handles inconsistent naming conventions across teams and platforms.
 */

export const AD_CLICK_IDS = {
  // ── Google ─────────────────────────────────────────────────────────────
  gclid:      { platform: 'google',    medium: 'paid_search' },   // Google Ads (Search, Shopping)
  gbraid:     { platform: 'google',    medium: 'paid_search' },   // Google Ads iOS app (privacy-safe)
  wbraid:     { platform: 'google',    medium: 'paid_search' },   // Google Ads web-to-app (privacy-safe)
  gclsrc:     { platform: 'google',    medium: 'paid_search' },   // Google SA360 / DoubleClick Search
  dclid:      { platform: 'google',    medium: 'display'     },   // Google Display & Video 360

  // ── Microsoft ──────────────────────────────────────────────────────────
  msclkid:    { platform: 'microsoft', medium: 'paid_search' },   // Microsoft / Bing Ads

  // ── Meta ───────────────────────────────────────────────────────────────
  fbclid:     { platform: 'meta',      medium: 'paid_social' },   // Facebook & Instagram Ads

  // ── TikTok ─────────────────────────────────────────────────────────────
  ttclid:     { platform: 'tiktok',    medium: 'paid_social' },   // TikTok Ads

  // ── X / Twitter ────────────────────────────────────────────────────────
  twclid:     { platform: 'twitter',   medium: 'paid_social' },   // X (Twitter) Ads

  // ── LinkedIn ───────────────────────────────────────────────────────────
  li_fat_id:  { platform: 'linkedin',  medium: 'paid_social' },   // LinkedIn Ads

  // ── Snapchat ───────────────────────────────────────────────────────────
  ScCid:      { platform: 'snapchat',  medium: 'paid_social' },   // Snapchat Ads (case-sensitive)
  sccid:      { platform: 'snapchat',  medium: 'paid_social' },   // Snapchat Ads (lowercase variant)

  // ── Pinterest ──────────────────────────────────────────────────────────
  epik:       { platform: 'pinterest', medium: 'paid_social' },   // Pinterest Ads

  // ── Reddit ─────────────────────────────────────────────────────────────
  rdt_cid:    { platform: 'reddit',    medium: 'paid_social' },   // Reddit Ads

  // ── Seznam / Sklik (CZ) ────────────────────────────────────────────────
  sznclid:    { platform: 'seznam',    medium: 'paid_search' },   // Seznam Sklik (Czech market)

  // ── Affiliate networks ─────────────────────────────────────────────────
  irclickid:  { platform: 'impact',    medium: 'affiliate'   },   // Impact Radius / Rakuten
  clickid:    { platform: 'affiliate', medium: 'affiliate'   },   // Generic affiliate (CJ, Awin, etc.)

  // ── Email platforms ────────────────────────────────────────────────────
  _kx:        { platform: 'klaviyo',   medium: 'email'       },   // Klaviyo
  mc_cid:     { platform: 'mailchimp', medium: 'email'       },   // Mailchimp campaign ID
  mc_eid:     { platform: 'mailchimp', medium: 'email'       },   // Mailchimp email ID
};

/**
 * Normalizes raw utm_medium values to a canonical channel bucket.
 * Handles common misspellings and inconsistent naming across teams.
 */
export const UTM_MEDIUM_MAP = {
  // Paid search
  cpc:          'paid_search',
  ppc:          'paid_search',
  paid_search:  'paid_search',
  paidsearch:   'paid_search',
  search:       'paid_search',

  // Paid social
  paid_social:  'paid_social',
  paidsocial:   'paid_social',
  'paid-social':'paid_social',
  paid:         'paid_social',   // generic "paid" — assumed social if no click ID

  // Display
  display:      'display',
  banner:       'display',
  cpm:          'display',
  retargeting:  'display',
  remarketing:  'display',

  // Email
  email:        'email',
  newsletter:   'email',
  edm:          'email',

  // Affiliate
  affiliate:    'affiliate',
  partner:      'affiliate',

  // Organic social
  social:       'organic_social',
  organic_social: 'organic_social',
  'organic-social': 'organic_social',
};
