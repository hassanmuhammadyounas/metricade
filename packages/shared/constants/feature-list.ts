/**
 * All 51 features in order — must match featurizer.py exactly.
 * This is the source of truth for the feature vector schema.
 *
 * Tier 1 — Critical Signal (indices 0–10, ~70% of detection power)
 * Tier 2 — High Signal (indices 11–30)
 * Tier 3 — Contextual (indices 31–50)
 */
export const FEATURES = [
  // Tier 1 — Critical Signal
  'event_type_INIT',              // 0  — one-hot
  'event_type_PAGE_VIEW',         // 1
  'event_type_SCROLL',            // 2
  'event_type_TOUCH_END',         // 3
  'event_type_CLICK',             // 4
  'event_type_TAB_HIDDEN',        // 5
  'event_type_TAB_VISIBLE',       // 6
  'delta_ms',                     // 7  — normalized by 10000
  'scroll_velocity_px_s',         // 8  — normalized by 1000
  'scroll_acceleration',          // 9  — normalized by 500
  'y_reversal',                   // 10 — binary 0/1

  // Tier 2 — High Signal
  'scroll_depth_pct',             // 11 — normalized by 100
  'tap_interval_ms',              // 12 — normalized by 5000
  'contact_radius',               // 13 — normalized by 50
  'dead_tap',                     // 14 — binary 0/1
  'force',                        // 15
  'click_x',                      // 16 — normalized by 2560
  'click_y',                      // 17 — normalized by 1440

  // Indices 18–50 — reserved for future features
  // Add here as featurizer.py is expanded
  'reserved_18',
  'reserved_19',
  'reserved_20',
  'reserved_21',
  'reserved_22',
  'reserved_23',
  'reserved_24',
  'reserved_25',
  'reserved_26',
  'reserved_27',
  'reserved_28',
  'reserved_29',
  'reserved_30',
  'reserved_31',
  'reserved_32',
  'reserved_33',
  'reserved_34',
  'reserved_35',
  'reserved_36',
  'reserved_37',
  'reserved_38',
  'reserved_39',
  'reserved_40',
  'reserved_41',
  'reserved_42',
  'reserved_43',
  'reserved_44',
  'reserved_45',
  'reserved_46',
  'reserved_47',
  'reserved_48',
  'reserved_49',
  'reserved_50',
] as const;

export type FeatureName = typeof FEATURES[number];
