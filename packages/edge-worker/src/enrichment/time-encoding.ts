// Cyclic sin/cos encoding for hour-of-day and day-of-week
// This preserves the circular nature of time (23:59 is close to 00:00)

export type TimeFeatures = {
  hour_sin: number;
  hour_cos: number;
  dow_sin: number;
  dow_cos: number;
  local_hour: number;
  is_weekend: 0 | 1;
};

export function encodeTime(timestampMs: number): TimeFeatures {
  const d = new Date(timestampMs);
  const hour = d.getUTCHours() + d.getUTCMinutes() / 60;
  const dow = d.getUTCDay();

  return {
    hour_sin:   Math.sin((2 * Math.PI * hour) / 24),
    hour_cos:   Math.cos((2 * Math.PI * hour) / 24),
    dow_sin:    Math.sin((2 * Math.PI * dow) / 7),
    dow_cos:    Math.cos((2 * Math.PI * dow) / 7),
    local_hour: d.getUTCHours(),
    is_weekend: (dow === 0 || dow === 6) ? 1 : 0,
  };
}
