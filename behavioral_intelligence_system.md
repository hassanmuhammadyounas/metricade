**Behavioral Intelligence System**

Technical Architecture & Design Reference

*Fraud Detection · Intent Classification · Behavioral Analytics*

**01 What We Are Building**

This system is a self-supervised behavioral intelligence platform that
collects granular user interaction data from web browsers, encodes that
data into high-dimensional vector representations using a Transformer
neural network, and clusters those vectors to automatically identify
distinct behavioral cohorts --- including fraud bots, high-intent
buyers, casual browsers, and non-commercial visitors --- without
requiring any labeled training data.

The system is designed to be entirely store-agnostic and
environment-agnostic. It does not rely on product identifiers, page
labels, or any site-specific metadata. It learns behavioral patterns
from the raw physics of how people interact with a page: how fast they
scroll, whether they reverse direction, how long they pause, how they
tap, and how all of these signals evolve over the course of a session.

**Core Objectives**

-   Detect non-human traffic (bots, click farms, scrapers) before it
    distorts analytics or wastes ad spend

-   Identify high-intent users whose behavioral signature predicts
    commercial conversion

-   Separate non-commercial visitors (researchers, agencies,
    competitors) from genuine buyers

-   Produce validated, interpretable cohort labels without manual
    annotation

-   Operate in real time with sub-second vector storage and retrieval

**What Makes This Different from Standard Analytics**

Standard analytics tools count events --- pageviews, clicks, sessions.
They do not model the physics of how a human moves. A bot and a human
can produce identical pageview counts while having completely different
scroll velocity distributions, acceleration profiles, and interaction
timing. This system operates on the physics layer, not the count layer.
The fraud signal is not in what happened, but in how it happened.

**02 System Architecture**

The full pipeline runs across three layers: browser, server, and
storage. Each layer has a distinct responsibility and they communicate
via a buffered HTTP transport that tolerates tab closures and network
failures gracefully.

**End-to-End Pipeline**

  ---------------- ------------------------------------------------------------
  **BROWSER**      pixel.js runs in the visitor\'s browser. It captures scroll
                   physics, touch interactions, click patterns, tab visibility
                   changes, and page navigation events. Events are buffered in
                   memory and flushed to the server every 30 events or 10
                   seconds, whichever comes first. On tab close, sendBeacon
                   ensures the final payload is delivered even after the page
                   is gone.

  **SERVER**       The API endpoint receives each payload, reads the client IP
                   address from request headers, enriches it via IP geolocation
                   API (ip_type, ip_country, ASN), parses the User-Agent header
                   into structured browser and device fields, and computes
                   time-of-day cyclical features from the session timestamp.
                   The enriched event batch is published to a Redis pub/sub
                   channel for downstream processing.

  **ML WORKER**    A subscriber worker receives the enriched event batch from
                   Redis. It assembles the full session feature matrix, runs it
                   through the trained Transformer encoder to produce a
                   192-dimensional session vector, and upserts that vector to
                   the vector database with session metadata attached.

  **STORAGE**      Upstash provides two services: Redis for pub/sub event
                   ingestion and raw event audit trail, and Vector for
                   serverless 192-dim fingerprint storage with approximate
                   nearest-neighbor search. Both are serverless and scale to
                   zero at idle --- cost is per-request only. A 192-dim vector
                   is approximately 1.5KB; 10,000 sessions per month is roughly
                   15MB.

  **CLUSTERING**   Periodically (e.g. nightly), all stored vectors are pulled
                   from Upstash Vector and passed through HDBSCAN or K-means
                   clustering. Natural groupings emerge from the geometry of
                   the vector space. Each cluster is profiled by computing the
                   mean of raw behavioral features across all its member
                   sessions. Labels (FRAUD_BOT, HIGH_INTENT, LOW_INTENT, etc.)
                   are assigned automatically via rule-based thresholds on the
                   profile.
  ---------------- ------------------------------------------------------------

**03 Identity System**

Every event carries three distinct identifiers that answer three
different questions. This hierarchy is critical for understanding
multi-tab behavior, repeat visits, and cross-session patterns.

  ------------ ---------------- ---------------- ---------------------------
  **ID Field** **Storage**      **Scope**        **Purpose**

  client_id    localStorage     Same device, all Links all sessions from the
                                tabs, permanent  same browser. Detects
                                                 repeat fraud infrastructure
                                                 and cross-session patterns.

  session_id   sessionStorage   One tab, one     Tab-isolated by browser
                                visit, resets on spec. Two tabs open
                                tab close        simultaneously each get
                                                 their own session_id
                                                 automatically --- no extra
                                                 logic required.

  page_id      In-memory only   One page render, Groups all events from a
                                resets on        single page render.
                                navigation       Regenerated on popstate and
                                                 hashchange events for SPA
                                                 routing support.
  ------------ ---------------- ---------------- ---------------------------

**Why Tab Isolation Matters**

A genuine user opening two product tabs simultaneously produces two
independent sessions with two independent session_ids. Both sessions
share a client_id, linking them to the same device. A fraud bot
typically hits pages sequentially with page_load_index always equal to 1
--- it never builds up a multi-page session because it restarts the
script on each run. Genuine users average 2.3+ pages per session before
an add-to-cart action. This asymmetry is a strong fraud signal captured
automatically by the page_load_index field.

**Multi-Tab Fraud Pattern**

When a single client_id produces 8 or more sessions within 60 seconds,
each with identical scroll velocity and zero reversals, that is a bot
cycling through product pages. The client_id links what would otherwise
appear to be independent sessions into a coordinated pattern. Without
client_id, each session looks borderline. With it, the pattern is
unambiguous.

**04 Browser Data Collection --- pixel.js**

pixel.js is a single vanilla JavaScript file that runs in the visitor\'s
browser. It requires no dependencies, wraps everything in an IIFE to
avoid global scope pollution, and works in all browsers including in-app
browsers (Facebook, Instagram, WeChat, TikTok WebViews).

**Event Types Captured**

  --------------- -------------------------------------------------------
  **Event Type**  **Description**

  INIT            Fires once on script load, before any user interaction.
                  Records full session baseline --- device, browser
                  environment, paid media status, timezone. delta_ms = 0.
                  This is the initialization event that establishes the
                  session context.

  PAGE_VIEW       Fires on initial load and on every popstate /
                  hashchange event. Increments page_load_index,
                  regenerates page_id, recomputes page_path_hash. Fraud
                  scripts almost always have page_load_index = 1.

  SCROLL          Fires on every scroll event (rAF-throttled at 16ms
                  minimum). Carries full scroll physics: velocity,
                  acceleration, direction, reversal flag, depth
                  percentage, pause duration.

  TOUCH_END       Fires on touchend on mobile / touch devices. Carries
                  tap interval, long press duration, contact area radius,
                  pressure force, and dead_tap flag.

  CLICK           Fires on click events on non-touch devices only (avoids
                  double-firing on mobile). Carries position coordinates,
                  tap interval, and dead_tap flag.

  TAB_HIDDEN      Fires when the user switches away from the tab or
                  minimizes the window. Uses document.addEventListener
                  for Safari \< 14 compatibility. Triggers an immediate
                  buffer flush.

  TAB_VISIBLE     Fires when the user returns to the tab. Together with
                  TAB_HIDDEN, measures total time the tab was active vs
                  backgrounded.
  --------------- -------------------------------------------------------

**Buffer and Flush Strategy**

Events are not sent to the server one by one. This would create 60+ HTTP
requests per second during fast scrolling, overwhelming both the server
and the client device battery. Instead, events are collected in a local
in-memory array and flushed in four specific situations:

  ---------------------- ------------------------------------------------
  **Flush Trigger**      **Reason**

  30 events accumulated  Prevents the buffer from growing too large. A
                         fraud session is typically 4--8 events total ---
                         guaranteed to be captured in the first flush.

  10 seconds elapsed     Keeps data flowing to the server for real-time
  since last flush       scoring while the session is active. Means
                         maximum 10 seconds of data is ever lost if the
                         browser crashes.

  visibilitychange →     User is leaving the tab. Flush immediately using
  hidden                 sendBeacon (queued at OS level, fires even after
                         the page is gone).

  pagehide event         Safari fallback. Safari does not reliably fire
                         visibilitychange on navigation. pagehide is the
                         reliable alternative. A 100ms dedup guard
                         prevents both events from double-flushing.
  ---------------------- ------------------------------------------------

Transport selection: sendBeacon is used when document.visibilityState
=== \'hidden\' because the page is unloading and a normal fetch would be
killed mid-flight. fetch with keepalive: true is used when the page is
active, as it provides better error handling and response visibility.

**05 Feature Engineering --- The 51 Features**

Features are organized into three tiers based on their contribution to
fraud detection signal. Scores are based on cross-referencing ACM
Computing Surveys (2023), EURASIP (2025), and multiple behavioral
biometrics research papers. Store-agnostic design is enforced
throughout: no SKU, no page labels, no site-specific metadata.

**Tier 1 --- Critical Signal (Score 9--10, \~70% of detection power)**

  ---------------------- ----------- -------------------------------------------------
  **Feature**            **Score**   **Why It Matters**

  event_type             **10**      The sequence of event types is the primary input
                                     to the Transformer. PAGE_VIEW → SCROLL → SCROLL →
                                     CLICK tells a different story than PAGE_VIEW →
                                     SCROLL → SCROLL → SCROLL → SCROLL.

  delta_ms               **10**      Milliseconds between consecutive events. Fraud
                                     bots produce machine-precise timing (340ms ±
                                     2ms). Humans produce noisy timing (200--800ms
                                     with high variance).

  scroll_velocity_px_s   **10**      Pixels per second at the moment of each scroll
                                     event. Fraud signature: constant band of 205--255
                                     px/s. Genuine human range: 20--600 px/s with high
                                     variance.

  scroll_acceleration    **10**      Rate of velocity change between scroll events.
                                     Fraud: near-zero (constant velocity). Human:
                                     40--120 px/s² variance. ACM survey identified
                                     this as top discriminator.

  y_reversal             **10**      Boolean: did scroll direction reverse vs the
                                     previous scroll event? Fraud bots never reverse
                                     (0.00 per session). Genuine users reverse 7--18%
                                     of scroll events while reading.

  scroll_direction       **10**      Current scroll direction (+1 down, -1 up).
                                     Combined with y_reversal creates the most
                                     powerful single fraud signal in the feature set.

  scroll_depth_pct       **9**       How far down the page the user has scrolled,
                                     normalized 0.0--1.0. Fraud bots scroll to a fixed
                                     depth consistently. Humans vary with page
                                     content.

  patch_x / patch_y      **9**       Normalized viewport coordinates of scroll
                                     position, clicks, and touches. The Transformer
                                     learns spatial patterns associated with specific
                                     page regions without knowing what the regions
                                     are.

  page_path_hash         **9**       djb2 hash of the URL pathname. Enables the model
                                     to learn behavioral patterns associated with
                                     specific page types (product, collection,
                                     checkout) without hardcoding labels.

  page_id                **9**       Fresh UUID per page render. Groups events to the
                                     same render context. Identifies when a user
                                     reloads vs navigates.

  page_load_index        **9**       Integer sequence 1, 2, 3\... per page view in
                                     session. Fraud scripts hit the product page as
                                     index=1. Genuine users average 2.3+ pages before
                                     ATC.
  ---------------------- ----------- -------------------------------------------------

**Tier 2 --- Strong Signal (Score 7--8, brings total to \~90%)**

  -------------------------- ----------- -------------------------------------------------
  **Feature**                **Score**   **Why It Matters**

  scroll_pause_duration_ms   **8**       Duration of gap since last scroll event (recorded
                                         if \>500ms). Humans pause to read. Fraud bots
                                         scroll continuously with zero pauses.

  tap_interval_ms            **8**       Milliseconds between consecutive touch/click
                                         events. Machine-precise intervals are a strong
                                         bot signal on mobile.

  long_press_duration_ms     **8**       Duration of touch contact. Accidental taps are
                                         \~80ms. Intentional taps 120--300ms. Long presses
                                         500ms+. Bots produce uniform durations.

  dead_tap                   **8**       True if the tap target has no interactive handler
                                         (not a link, button, input, etc.). High dead_tap
                                         rate indicates automated coordinate-based
                                         clicking rather than intent-driven clicking.

  is_touch                   **8**       Whether the device is a touch device. Fraud bots
                                         frequently claim to be mobile to avoid desktop
                                         bot detection, but their scroll physics do not
                                         match mobile behavior.

  is_webview                 **7**       Whether the session is inside an in-app browser.
                                         Click farms heavily use WebViews to simulate
                                         app-driven traffic.

  is_paid / paid_platform    **8**       Whether the session arrived from a paid ad click
                                         and which platform. Fraud is disproportionately
                                         concentrated on paid traffic. Enables
                                         per-platform fraud rate analysis.

  click_id_type              **7**       The specific click ID parameter (gclid, fbclid,
                                         ttclid, etc.). Different ad platforms have
                                         different fraud profiles.

  ip_type                    **8**       RESIDENTIAL / DATACENTER / VPN / MOBILE_CARRIER.
                                         Datacenter IPs rarely belong to genuine shoppers.
                                         Server-side enrichment via IP geolocation API.

  ip_country                 **7**       ISO country code of the visitor\'s IP.
                                         Cross-referenced against site\'s target market
                                         geography.

  ip_asn_type                **7**       Autonomous System Name of the IP --- identifies
                                         hosting providers, cloud services, and known
                                         proxy networks.
  -------------------------- ----------- -------------------------------------------------

**Tier 3 --- Enrichment Signal (Score 5--6, contextual value)**

  ---------------------- ----------- -------------------------------------------------
  **Feature**            **Score**   **Why It Matters**

  device_pixel_ratio     **6**       Unusual values (exactly 1.0 on claimed mobile, or
                                     very high values) can indicate emulated
                                     environments.

  viewport_w_norm /      **6**       Normalized viewport dimensions. Headless browsers
  viewport_h_norm                    often have non-standard viewport ratios.

  hardware_concurrency   **5**       CPU core count. Capped at 8 by Firefox/Safari.
                                     Mismatches between claimed device type and core
                                     count are a weak fraud signal.

  browser_timezone       **7**       Browser\'s reported timezone
                                     (Intl.DateTimeFormat). Server compares against IP
                                     geolocation timezone to detect VPN mismatch.

  ua_browser_family      **6**       Browser family parsed from User-Agent header
                                     (server-side). Cannot be spoofed at the network
                                     layer. Chrome, Safari, Facebook, etc.

  ua_os_family /         **6**       OS and device parsed from User-Agent.
  ua_device_family                   Cross-referenced against is_touch and
                                     device_pixel_ratio for consistency.

  hour_sin / hour_cos    **5**       Cyclical encoding of local hour of day. Avoids
                                     the midnight discontinuity (23:59 and 00:01 are
                                     adjacent). Weak for fraud detection, stronger for
                                     intent prediction.

  dow_sin / dow_cos      **5**       Cyclical encoding of day of week. Weekend vs
                                     weekday behavioral shifts are real but subtle.

  tap_pressure           **5**       Touch force (0.0--1.0). May be 0 if hardware does
                                     not support pressure sensing. Stored when
                                     available.

  tap_radius_x /         **5**       Touch contact area dimensions. Returns 1 if
  tap_radius_y                       hardware does not report area. Uniform radius
                                     across all taps is a mild bot signal.
  ---------------------- ----------- -------------------------------------------------

**06 Server-Side Enrichment**

Three categories of data cannot be collected in the browser. They are
added by the API endpoint when it receives each event payload from
pixel.js.

**IP Enrichment**

The client IP address is read from the incoming request headers ---
req.headers\[\'x-forwarded-for\'\] behind a proxy, or
req.socket.remoteAddress directly. JavaScript running in the browser has
no access to the raw IP address. The IP geolocation lookup is performed
once per session, not per event.

  ------------------- ----------------------------------------------------
  **Field**           **Derivation**

  ip_type             DATACENTER if is_hosting flag set. VPN if is_proxy
                      flag set. MOBILE_CARRIER if is_mobile flag set.
                      RESIDENTIAL otherwise.

  ip_country          ISO 3166-1 alpha-2 country code from geolocation
                      lookup.

  ip_asn_type         Autonomous System Name --- identifies the network
                      operator (ISP, cloud provider, hosting service).

  ip_is_blocked       Boolean. True if IP is flagged as proxy or hosting
                      provider.

  timezone_mismatch   Boolean. True if browser\'s Intl.DateTimeFormat
                      timezone (sent in pixel payload) does not match the
                      timezone derived from IP geolocation. Detects VPN
                      users claiming a different geography.
  ------------------- ----------------------------------------------------

**User Agent Enrichment**

The User-Agent HTTP header is parsed server-side using a UA parser
library. The network-level User-Agent cannot be overridden by JavaScript
running in the page --- only the browser itself sets this header. This
makes it tamper-resistant compared to navigator.userAgent which a fraud
script can override.

  -------------------- ------------------ ----------------------------------
  **Field**            **Example Value**  **Notes**

  ua_browser_family    Chrome, Safari,    Facebook and Instagram in-app
                       Facebook           browsers identify themselves
                                          distinctly.

  ua_browser_version   122                Major version only is sufficient.

  ua_os_family         iOS, Android,      Cross-reference against is_touch
                       Windows            from pixel.js for consistency.

  ua_os_version        17                 iOS 17, Android 14, etc.

  ua_device_family     iPhone, Samsung    Device model when available from
                       SM-G991            UA string.
  -------------------- ------------------ ----------------------------------

**Time Feature Encoding**

Time features are derived server-side from the session timestamp
combined with the IP-derived timezone. Raw hour and day-of-week values
are encoded cyclically to prevent the midnight discontinuity --- hour 23
and hour 0 are adjacent in time but would appear far apart if encoded as
raw integers.

**The cyclical encoding uses sine and cosine pairs:**

> hour_sin = sin(2π × local_hour / 24)
>
> hour_cos = cos(2π × local_hour / 24)
>
> dow_sin = sin(2π × day_of_week / 7)
>
> dow_cos = cos(2π × day_of_week / 7)

These four values plus is_weekend and local_hour (raw integer for
dashboards) are repeated on every event row. Time features are weak for
fraud detection --- click farms operate 24/7 in shifts and their
behavioral signature is identical at 2am and 2pm. Time features are more
valuable for intent prediction, where genuine user behavior varies
meaningfully by time of day.

**07 The Machine Learning Model**

The model is a Transformer encoder trained with SimCLR contrastive
self-supervision. It takes a variable-length sequence of behavioral
events and produces a fixed 192-dimensional vector that encodes the
behavioral signature of the entire session.

**Model Specifications**

  ---------------------- ------------------------------------------------
  **Parameter**          **Value**

  Architecture           Transformer Encoder (not decoder --- no text
                         generation, only sequence encoding)

  Total parameters       455,000 (\~455K)

  Output embedding       192 dimensions
  dimension              

  Input                  Variable-length event sequence, each event as a
                         vector of 30--51 features

  Training method        SimCLR contrastive self-supervision (no labels
                         required)

  Training data          5,000+ behavioral sessions (synthetic and real)

  Model name (internal)  behavioral-encoder-v1
  ---------------------- ------------------------------------------------

**The Transformer Encoder --- How It Works**

A Transformer encoder reads a sequence of items and produces a
context-aware representation of the whole sequence. In this system, the
sequence is the list of events in a session. Each event is a row of
numbers (scroll velocity, delta_ms, patch_x, etc.).

The core operation inside every Transformer layer is self-attention.
Every event in the sequence looks at every other event and asks: how
relevant are you to understanding me? Mathematically:

***Attention(Q, K, V) = softmax(QK\^T / sqrt(d_k)) × V***

In plain language: Q (queries), K (keys), and V (values) are learned
linear projections of the event representations. The dot product QK\^T
measures similarity between every pair of events. Dividing by sqrt(d_k)
prevents the similarity scores from becoming too large. The softmax
converts the scores to a probability distribution. The output is a
weighted sum of all value vectors --- each event\'s new representation
incorporates information from the events most relevant to it.

For example, a scroll event at position 3 in the sequence might discover
through attention that the ATC click at position 40 (340ms later) is
highly relevant to understanding its own context. The attention
mechanism learns these relationships automatically from training data.

After multiple attention layers, the final representations of all events
are averaged (mean pooling) to produce a single 192-dimensional vector
that summarizes the entire session. This vector is the session
fingerprint.

**Why 192 Dimensions**

192 was chosen as a balance between representational capacity and
practical efficiency. Too few dimensions (e.g. 32) cannot encode all the
complexity of behavioral patterns --- different session types get
squashed together in the vector space. Too many dimensions (e.g. 1024)
wastes compute and storage, and can hurt clustering because the space
becomes too sparse for nearest-neighbor algorithms to work well. 192 is
also a multiple of 64, which aligns well with GPU memory allocation.

**08 SimCLR --- Contrastive Self-Supervised Training**

SimCLR stands for Simple Framework for Contrastive Learning of
Representations. It was developed by Google Brain in 2020. The framework
teaches the Transformer what \'similar\' means without ever seeing
labels. It only runs during the training phase --- once training is
complete, SimCLR is discarded and only the trained Transformer weights
are kept.

**The Problem SimCLR Solves**

Before training, the Transformer\'s weights are random. It encodes two
fraud sessions and produces two random 192-dim vectors. These vectors
bear no relationship to each other --- they could be on completely
opposite sides of the 192-dim space. Clustering on these random vectors
produces meaningless garbage. SimCLR fixes this by calibrating the
Transformer to produce geometrically meaningful vectors.

**How SimCLR Works --- Step by Step**

Step 1 --- Augmentation. Take one real session (the full event sequence
--- all 40 events). Create two slightly different versions of it (called
augmented views). View 1: drop 10% of scroll events randomly, add ±5ms
noise to all delta_ms values. View 2: drop a different random 10% of
scroll events, add different noise to delta_ms. These two views are
imperfect versions of the same session, but they both still carry the
same core behavioral signature.

Step 2 --- Encoding. Feed a batch of 256 sessions into the Transformer.
Each session produces two views. 512 vectors total come out of the
Transformer. Each vector is then passed through a small projection head
(two linear layers) to produce projected vectors z1 and z2.

Step 3 --- The Contrastive Loss. The NT-Xent (Normalized
Temperature-scaled Cross Entropy) loss asks: for View 1 of Session A,
which of the other 511 vectors is its correct pair? The model must
identify View 2 of Session A as the match, out of 510 impostors. The
loss is:

***L = -log\[ exp(sim(z1, z2) / τ) / Σ exp(sim(z1, zk) / τ) \]***

Where sim() is cosine similarity, τ (tau) is a temperature parameter
(\~0.07) that sharpens the distribution, and the sum runs over all other
vectors in the batch. The loss goes down when the model consistently
identifies the correct pair. Transformer weights are updated via
backpropagation after each batch.

**Why This Creates Useful Geometry**

All fraud sessions share the same core behavioral signature: constant
scroll velocity \~228 px/s, zero reversals, 340ms ATC timing. When two
augmented copies of a fraud session are created, both still carry this
signature. The model learns to map them close together in the 192-dim
space. Genuine sessions are all different from each other --- varied
velocity, pauses, reversals. After training on thousands of sessions,
the Transformer has learned:

-   \'Constant velocity + zero reversals + 340ms ATC timing\' → this
    region of the 192-dim space

-   \'High pauses + many reversals + deep scroll\' → this other region

-   \'Fast navigation + shallow depth + zero clicks\' → a third region

Nobody encoded these rules. They fell out naturally from the training
objective.

**The Camera Analogy**

Think of the Transformer as a camera. Before SimCLR, the lens is
completely out of focus. It photographs a fraud session and a genuine
session --- both photos look like random blur, indistinguishable. SimCLR
is the process of adjusting the lens until similar things look similar
and different things look different. After training, the focusing tool
(SimCLR) is discarded. The lens stays focused permanently. Every new
session photographed with this calibrated lens produces a sharp,
geometrically meaningful 192-dim vector.

**09 Clustering and Cohort Identification**

Clustering runs periodically on all stored session vectors. It does not
require labels and does not know anything about fraud, intent, or
commercial behavior. It finds natural groupings in the 192-dim vector
space based purely on geometric proximity.

**The Clustering Algorithm --- HDBSCAN**

HDBSCAN (Hierarchical Density-Based Spatial Clustering of Applications
with Noise) identifies clusters by finding regions of the vector space
where points are densely packed. Unlike K-means, it does not require
specifying the number of clusters in advance. It outputs an integer
label for each session (0, 1, 2, \...) and assigns -1 to sessions that
do not belong to any dense cluster (noise points).

**Cluster Profiling**

After clusters form, the mean value of every raw behavioral feature is
computed across all sessions in each cluster. This produces a
human-readable profile that makes the cluster\'s identity obvious:

  ------------- ---------------- ----------------- --------------- ---------------- -------------- ------------
  **Cluster**   **scroll_vel**   **y_reversals**   **pauses_ms**   **page_depth**   **atc_rate**   **Auto
                                                                                                   Label**

  Cluster 0     80 px/s          0.12              1,200ms         0.45             0.03           LOW INTENT

  Cluster 1     45 px/s          0.18              2,800ms         0.78             0.21           HIGH INTENT

  Cluster 2     228 px/s         0.00              0ms             0.52             0.86           FRAUD BOT

  Cluster 3     42 px/s          0.21              3,200ms         0.85             0.00           RESEARCHER
  ------------- ---------------- ----------------- --------------- ---------------- -------------- ------------

**Automated Label Assignment**

Labels are assigned automatically using rule-based thresholds computed
from the cluster profile. The rules are set once after inspecting the
first clustering run, then applied automatically to every subsequent run
as new sessions accumulate.

> if mean_scroll_velocity \> 180 and mean_y_reversals \< 0.01:
>
> label = \'FRAUD_BOT\'
>
> elif mean_purchase_rate \> 0.10 or mean_atc_count \> 0.8:
>
> label = \'HIGH_INTENT\'
>
> elif mean_scroll_depth \< 0.3 and mean_page_load_index \< 2:
>
> label = \'LOW_INTENT\'
>
> else:
>
> label = \'MEDIUM_INTENT\'

**Commercial Signals as Validation --- Not Training Input**

Add-to-cart, checkout, and purchase events are NOT fed into the
Transformer or used to influence clustering. They are computed as
read-only statistics on top of the clusters after they form. This
separation is intentional and important.

If commercial signals influenced the clustering, the model would
optimize for finding buyers --- which requires labeled data (which
sessions purchased?) and would drown out the behavioral physics signal
that makes fraud detection possible. Keeping commercial signals as
validation-only means:

-   The clustering is honest --- it reflects behavioral reality, not
    commercial outcomes

-   The validation is meaningful --- if clusters separate cleanly on
    purchase rate, the behavioral features are genuinely predictive

-   The model works even on sites with no commercial events (pure
    content sites, informational pages)

**10 Behavioral Scenarios and How The System Handles Them**

**Scenario 1 --- Classic Fraud Bot**

A bot script loads a product page, executes a scroll sequence at
constant velocity, and fires an add-to-cart event after exactly 340ms.
It repeats this across hundreds of sessions.

-   scroll_velocity: constant 205--255 px/s band across all scroll
    events

-   scroll_acceleration: near-zero --- velocity does not change

-   y_reversal: 0.00 --- never reverses direction

-   scroll_pause_duration_ms: 0 --- no pauses

-   delta_ms: machine-precise, low variance

-   page_load_index: always 1 --- never builds a multi-page session

-   client_id: same device produces hundreds of sessions in hours

The Transformer encodes all these sessions into vectors that cluster
tightly together. The cluster profile makes the identity unambiguous:
high ATC rate, zero purchases, constant velocity, zero reversals.

**Scenario 2 --- High-Intent Genuine Buyer**

A real user arrives from a paid ad, browses a collection page, opens
multiple product tabs, scrolls deeply and repeatedly reverses to re-read
descriptions, pauses on product images, and completes a purchase.

-   scroll_velocity: variable, 30--200 px/s with high variance

-   y_reversal: 0.15--0.22 --- reads and re-reads content

-   scroll_pause_duration_ms: 1,500--4,000ms --- pauses on product
    details

-   page_load_index: 3--6 --- browses multiple pages before ATC

-   is_paid: true --- arrived from ad click

-   client_id: one device, session built up over 8--15 minutes

These sessions cluster in a region of the vector space that correlates
with high ATC and purchase rates when commercial validation is applied.

**Scenario 3 --- Agency / Competitor Research Traffic**

A marketing agency or competitor visits the site to research products,
pricing, and positioning. They spend significant time, read content
deeply, navigate to the contact page, but never show any commercial
intent.

-   session_duration: 5--12 minutes

-   page_load_index: 4--8 --- extensive multi-page navigation

-   scroll_depth_pct: 0.75--0.90 --- reading deeply

-   y_reversal: 0.18--0.25 --- re-reading content

-   page_path_hash: contact page hash appears in session

-   atc_rate: 0.00 --- no commercial action taken

These sessions cluster separately from both fraud bots (whose physics
are completely different) and genuine buyers (who show commercial
signals). The cluster is identifiable by high engagement metrics
combined with zero commercial conversion. This is the correct outcome
--- these users are real humans, their behavioral signal should not be
suppressed from ad platforms, and they represent no fraud risk.

**Scenario 4 --- Low-Engagement Bounce Traffic**

A user arrives (possibly from a low-quality ad placement), scrolls
briefly, and exits within 10 seconds without interacting.

-   session_duration: \< 15 seconds

-   page_load_index: 1

-   scroll_depth_pct: \< 0.20

-   y_reversal: 0.00--0.02 --- minimal interaction

-   click count: 0

These sessions form their own cluster distinct from bots (different
velocity physics) and from genuine short sessions (which still show
human-like velocity variation). The cluster is useful for identifying
traffic quality issues by source.

**Scenario 5 --- Site With No Commercial Events**

On a site with no add-to-cart, checkout, or purchase events --- a
content site, a lead generation page, or a site where commercial
instrumentation has not yet been added --- the system still produces
meaningful clusters.

Without commercial signals, clustering still identifies: fraud bots
(velocity signature), genuine engaged readers (deep scroll, many
reversals, long pauses), passive scanners (fast scroll, shallow depth,
no clicks), and navigational visitors (many page transitions, low scroll
depth per page). Commercial signals, when added, serve as validation to
confirm the clusters are behaviorally meaningful --- not as inputs that
drive the grouping.

**Scenario 6 --- Multi-Tab User**

A user opens three product tabs simultaneously to compare options. Each
tab runs its own pixel.js instance with its own session_id (because
sessionStorage is tab-isolated by the browser specification). All three
sessions share the same client_id from localStorage.

The three sessions are stored as three independent vectors in the vector
database. Each gets clustered based on its own behavioral signature. The
shared client_id allows the system to identify that these three sessions
came from the same device --- useful for detecting bots that open many
tabs simultaneously, and for understanding multi-tab comparison behavior
in genuine high-intent shoppers.

**11 Vector Storage --- Upstash Architecture**

Upstash provides both components of the storage layer under a single
platform with serverless, per-request pricing that scales to zero at
idle.

**Upstash Redis --- Event Ingestion and Audit Trail**

pixel.js fires sendBeacon at flush time to the API endpoint. The
endpoint publishes the enriched event batch to an Upstash Redis pub/sub
channel. A subscriber worker receives the batch, runs Transformer
inference, and writes the resulting vector to Upstash Vector. The raw
event rows are also written to Redis as an audit trail for replay,
retraining, and debugging purposes.

**Upstash Vector --- Session Fingerprint Storage**

Each session\'s 192-dim vector is upserted to Upstash Vector with the
session_id as the key and metadata fields attached (client_id,
cluster_label, ip_country, is_paid, timestamp). Approximate
nearest-neighbor search enables real-time similarity queries --- given a
new incoming session vector, find the N most similar historical sessions
and their cluster labels.

  ---------------------- ------------------------------------------------
  **Dimension**          **Value**

  Vector size            192 dimensions × 4 bytes = \~768 bytes per
                         vector

  With metadata overhead \~1.5KB per session

  10,000 sessions/month  \~15MB --- practically free on serverless
                         pricing

  Query type             Approximate nearest-neighbor (ANN) search

  API                    REST --- compatible with Vercel, Cloudflare
                         Workers, any serverless runtime
  ---------------------- ------------------------------------------------

**12 Implementation Notes and Critical Details**

**Scroll Listener Cross-Browser Implementation**

The scroll listener must be attached to BOTH document and window. Some
storefront themes (particularly on Shopify) scroll an inner div rather
than the window itself. Without the document listener, scroll events
from these themes are completely missed. Both listeners must use the {
passive: true } flag --- without it, the browser waits for the
JavaScript handler to complete before scrolling, causing visible jank on
every scroll event.

Scroll position must be read with a cross-browser fallback:
window.scrollY (modern browsers) falling back to
document.documentElement.scrollTop or document.body.scrollTop. Scroll
depth requires taking the maximum of document.body.scrollHeight and
document.documentElement.scrollHeight to handle different rendering
modes.

**Tab Visibility --- Safari Compatibility**

The visibilitychange event must be attached to document, not window.
Safari versions below 14 only support document.addEventListener for this
event. Additionally, Safari does not reliably fire visibilitychange when
navigating away from a page. A pagehide listener is required as a
fallback. Both events should share a 100ms dedup guard to prevent
double-flushing when both fire.

**WebView Detection**

The WebView detection regex must cover: FBAN\|FBAV (Facebook app),
Instagram, Twitter, MicroMessenger (WeChat), Line, Snapchat, wv (generic
Android WebView), and the iOS WebView pattern
(iPhone\|iPod\|iPad)(?!.\*Safari\\/). The iOS pattern works because iOS
WebViews omit the \'Safari/\' string from their user agent, while the
actual Safari browser always includes it.

**Storage Access Resilience**

Both localStorage and sessionStorage must be wrapped in try/catch.
Private browsing mode in Safari and some corporate environments block
Web Storage entirely --- access throws a SecurityError rather than
returning null. When storage throws, the system falls back to in-memory
variables: client_id and session_id are generated fresh and held only
for the current page load. The session is still tracked; it just cannot
be linked to prior sessions from the same device.


**13 Cluster Validation Framework**

The correctness of the clustering is assessed by checking whether
clusters that the model identified as different based purely on
behavioral signals also differ on commercial metrics that the model
never saw during training. If they do, the behavioral features are
genuinely predictive. If they do not, the feature set needs revision.

  --------------------- ------------- ------------- ------------- ---------------
  **Cluster Profile     **ATC Rate**  **Purchase    **Bounce      **Diagnosis**
  Pattern**                           Rate**        Rate**        

  High velocity, zero   High          \~0%          Low           Fraud Bot
  reversals, zero                                                 
  pauses                                                          

  Variable velocity,    High          High          Low           High Intent
  high reversals, long                                            Buyer
  pauses, multi-page                                              

  Deep scroll, many     \~0%          \~0%          Low           Researcher
  reversals, contact                                              
  page, zero ATC                                                  

  Shallow scroll, fast  \~0%          \~0%          High          Bounce / Low
  exit, no clicks,                                                Quality
  page_load_index=1                                               

  Moderate scroll,      Low           Low           Medium        Passive Browser
  occasional clicks,                                              
  single page                                                     
  --------------------- ------------- ------------- ------------- ---------------

If commercial validation rates are roughly equal across all clusters, it
means the behavioral signals captured are not predictive for this
specific site --- the feature set, the session volume, or the training
configuration needs adjustment. This feedback loop is how the model
improves over time as real traffic accumulates.

**14 Design Principles Summary**

-   Store-agnostic by design. No SKUs, no page labels, no brand-specific
    metadata. Spatial patches and page_path_hash replace all
    site-specific identifiers.

-   Browser-side collects what only the browser can know: scroll
    physics, touch biometrics, tab behavior, paid media attribution.

-   Server-side enriches what the browser cannot know: IP
    classification, real User-Agent string, geographic timezone.

-   Commercial signals (ATC, purchase) validate the model but do not
    train it. This keeps the behavioral signal honest.

-   Three identity levels (client_id / session_id / page_id) capture
    device, tab, and page contexts independently without confusion.

-   SimCLR trains the Transformer to produce geometrically meaningful
    vectors without any labeled fraud examples. Once trained, SimCLR is
    discarded.

-   Clustering is unsupervised. Cluster labels emerge from behavioral
    geometry, not from predefined categories.

-   Serverless storage at both layers (Redis + Vector) means cost scales
    with actual traffic --- zero at idle, pennies at low volume.

*Behavioral Intelligence System --- Technical Reference v1.0 \|
Confidential*
