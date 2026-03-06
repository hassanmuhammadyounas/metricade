// Public API: window.behavioralPixel.track()
// Allows the host site to emit custom commercial intent signals

export function createPublicApi(buffer, flush) {
  return {
    /**
     * Track a commercial event (add to cart, wishlist, checkout step, etc.)
     * @param {string} eventName - descriptive name, e.g. 'add_to_cart'
     * @param {Object} [metadata] - optional key/value pairs (kept store-agnostic)
     */
    track(eventName, metadata = {}) {
      buffer.push({
        event_type: 'COMMERCIAL',
        event_name: eventName,
        delta_ms: Date.now(),
        metadata,
      });
      // Commercial events always trigger an immediate flush
      flush('commercial_event');
    },
  };
}
