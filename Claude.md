# Metricate MVP - Project Plan & Documentation

**Project:** Metricate - Reverse ETL SaaS for BigQuery → Google Ads Offline Conversions  
**Date Started:** January 10, 2026  
**Status:** In Development

---

## 🎯 Project Overview

**Metricate** is a reverse ETL SaaS application that syncs offline conversion data from BigQuery to Google Ads. Users can:
- Connect their BigQuery data source
- Connect their Google Ads account
- Map fields between BigQuery and Google Ads
- Schedule automatic syncs
- View sync history and logs

---

## 🏗️ Tech Stack (Final Decisions)

### Frontend + Backend
- **Framework:** Next.js (App Router)
- **UI Components:** shadcn/ui (modern, copy-paste components)
- **Admin Panel:** Refine.dev (auto-generates CRUD)
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **API Layer:** tRPC (type-safe API routes)

### Backend Services
- **Job Queue:** Bull (Redis-based)
- **Job Monitoring UI:** Bull Board
- **API Testing UI:** tRPC Panel

### Database & Auth
- **Database:** PostgreSQL (via Supabase)
- **Authentication:** Supabase Auth
- **ORM/Client:** Supabase JS Client

### External Integrations
- **Source:** BigQuery (client's own projects)
- **Destination:** Google Ads API (v19+)
- **Credentials Storage:** PostgreSQL (encrypted)

### Development Tools
- **Package Manager:** npm
- **Code Quality:** ESLint + Prettier
- **Version Control:** Git
- **Deployment:** TBD (likely Vercel)

---

## 📊 Database Schema (Created)

### Supabase PostgreSQL Tables (4 tables)

#### 1. `bigquery_connections`
```sql
- id (uuid, primary key)
- user_id (uuid → auth.users)
- name (text) - e.g., "Production BigQuery"
- project_id (text) - GCP project ID
- dataset_id (text, nullable) - Default dataset
- service_account_key (text, encrypted) - JSON credentials
- status (text) - 'active', 'error', 'testing'
- last_tested_at (timestamptz)
- test_error (text, nullable)
- created_at, updated_at (timestamptz)
```

#### 2. `google_ads_connections`
```sql
- id (uuid, primary key)
- user_id (uuid → auth.users)
- name (text) - e.g., "Main Google Ads Account"
- customer_id (text) - Google Ads customer ID
- conversion_action_id (text, nullable) - Target conversion action (picked after test)
- developer_token (text, encrypted)
- service_account_key (text, encrypted) - Service Account JSON key
- login_customer_id (text, nullable) - For MCC accounts
- status (text) - 'active', 'error', 'testing'
- last_tested_at (timestamptz)
- test_error (text, nullable)
- created_at, updated_at (timestamptz)
```

#### 3. `syncs`
```sql
- id (uuid, primary key)
- user_id (uuid → auth.users)
- bigquery_connection_id (uuid → bigquery_connections)
- google_ads_connection_id (uuid → google_ads_connections)
- name (text) - e.g., "Daily Offline Conversions"
- query (text) - SQL query or view/table name
- field_mappings (jsonb) - Column mappings
- schedule (text, nullable) - Cron expression
- status (text) - 'draft', 'active', 'paused', 'error'
- last_run_at, next_run_at (timestamptz, nullable)
- created_at, updated_at (timestamptz)
```

#### 4. `sync_runs`
```sql
- id (uuid, primary key)
- sync_id (uuid → syncs)
- bull_job_id (text, nullable) - Bull queue reference
- status (text) - 'pending', 'running', 'completed', 'failed'
- trigger_type (text) - 'manual', 'scheduled', 'test'
- triggered_by_user_id (uuid → auth.users, nullable)
- records_queried, records_sent, records_failed (integer, nullable)
- started_at, completed_at (timestamptz)
- duration_ms (integer, nullable)
- error_message (text, nullable)
- created_at (timestamptz)
```

---

## 🔐 Supabase Project Details

**Project Name:** metricade  
**Project URL:** https://phovbgvdmqgyvokkvdtm.supabase.co  
**Region:** ap-southeast-1 (Singapore)  
**Database:** PostgreSQL 16  

**Credentials:** (Stored securely in `.env.local`)

---

## 🎨 Design Decisions

### Color Scheme
- **Primary:** Black & White (strictly)
- **Accent:** Grayscale shades
- **Theme:** Light + Dark mode toggle

### Typography
- **Font:** System fonts (fastest load time)
- **Style:** Clean, minimal, professional

### UI Philosophy
- Minimal setup required from user
- Auto-generate UI from database schema
- Focus on functionality over decoration
- Fast, responsive, accessible

---

## 🗺️ Application Architecture

```
┌─────────────────────────────────────────────┐
│  Next.js Frontend (React + shadcn/ui)       │
│  - User dashboard                           │
│  - Connection setup                         │
│  - Sync configuration                       │
│  - Logs & monitoring                        │
└────────────────┬────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────┐
│  Refine Admin Panel (Auto-generated)        │
│  - CRUD for all tables                      │
│  - Forms, tables, filters                   │
│  - Built-in auth                            │
└────────────────┬────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────┐
│  tRPC API Routes (Type-safe)                │
│  - connections.* (test, create, list)       │
│  - syncs.* (create, run, status)            │
│  - jobs.* (status, logs)                    │
└────────────────┬────────────────────────────┘
                 │
       ┌─────────┴─────────┐
       ↓                   ↓
┌──────────────┐    ┌─────────────────┐
│ PostgreSQL   │    │ Bull + Redis    │
│ (Supabase)   │    │ - Job queue     │
│ - Users      │    │ - Scheduling    │
│ - Conns      │    │ - Processing    │
│ - Syncs      │    └────────┬────────┘
│ - Runs       │             ↓
└──────────────┘    ┌─────────────────┐
                    │ Bull Worker     │
                    │ 1. Query BQ     │
                    │ 2. Transform    │
                    │ 3. Send to GAds │
                    │ 4. Log results  │
                    └─────────────────┘
```

---

## 📋 Development Phases

### ✅ Phase 1: Foundation (COMPLETED)
- [x] Evaluated tech stack options
- [x] Decided on Refine + Next.js + shadcn/ui
- [x] Set up Supabase project
- [x] Created database schema (4 tables)
- [x] Saved reference pipeline documentation

### 🔄 Phase 2: Setup (IN PROGRESS)
- [x] Initialize Refine + Next.js project (with example pages)
- [ ] Move project files to root directory
- [ ] Configure Supabase connection
- [ ] Set up shadcn/ui theme (Black & White)
- [ ] Add tRPC
- [ ] Add Bull + Redis
- [ ] Configure environment variables

### 📝 Phase 3: Core Features (NEXT)
- [ ] Build BigQuery connection flow
- [ ] Build Google Ads connection flow
- [ ] Build sync configuration UI
- [ ] Implement field mapping interface
- [ ] Add sync scheduler
- [ ] Build Bull worker

### 🧪 Phase 4: Testing & Polish
- [ ] Test BigQuery integration
- [ ] Test Google Ads integration
- [ ] Test end-to-end sync flow
- [ ] Add error handling
- [ ] Build dashboard
- [ ] Add Bull Board monitoring

### 🚀 Phase 5: Deployment
- [ ] Choose hosting (Vercel/other)
- [ ] Set up CI/CD
- [ ] Deploy to production
- [ ] Test with real data

---

## 🔑 Key Features (MVP)

### User Features
1. **Sign Up / Login** (Supabase Auth)
2. **Add BigQuery Connection**
   - Upload service account JSON
   - Test connection
   - Save encrypted credentials
3. **Add Google Ads Connection**
   - OAuth flow
   - Select conversion action
   - Save tokens
4. **Create Sync**
   - Select source & destination
   - Provide BigQuery query/table
   - Map fields (BigQuery → Google Ads)
   - Set schedule (cron)
5. **View Sync History**
   - List all runs
   - See success/failure counts
   - View errors
6. **Manual Sync Trigger**
   - Run sync on-demand
   - See real-time progress

### Technical Features
1. **Auto-generated CRUD** (via Refine)
2. **Type-safe APIs** (via tRPC)
3. **Job Queue** (via Bull)
4. **Monitoring UI** (via Bull Board)
5. **API Testing** (via tRPC Panel)

---

## 🚫 What We're NOT Building (MVP)

- ❌ Team/workspace management (single user only)
- ❌ Billing/subscriptions
- ❌ Email notifications
- ❌ Advanced analytics/charts
- ❌ Multiple destination types (Google Ads only)
- ❌ Multiple source types (BigQuery only)
- ❌ Custom transformations (client's BigQuery handles)
- ❌ Data storage (client's BigQuery handles)
- ❌ Advanced scheduling options
- ❌ Webhook integrations
- ❌ Mobile app

---

## 📚 Reference Implementation

See sections below for complete documentation of the reference pipeline that inspired this project.

**Source Folder:** `google-ads-secondary-conversion_function-source/` (now deleted)  
**Purpose:** Python-based reverse ETL for Google Ads offline conversions  

---

## Table of Contents

1. [Architecture Overview](#architecture-overview-reference)
2. [File Structure](#file-structure)
3. [Dependencies](#dependencies)
4. [Detailed File Documentation](#detailed-file-documentation)
5. [Data Flow](#data-flow)
6. [Key Implementation Details](#key-implementation-details)
7. [Error Handling](#error-handling)
8. [Integration Points](#integration-points)

---

## Architecture Overview (Reference)

### Technology Stack
- **Runtime:** Google Cloud Functions (Python 3.x)
- **Framework:** Functions Framework (`functions-framework`)
- **Source:** Google BigQuery
- **Destination:** Google Ads API (v19)
- **Credentials:** Google Cloud Secret Manager
- **Monitoring:** Asana (task creation for run summaries)
- **Logging:** Structured logging with context

### Pipeline Flow
```
HTTP Trigger → Check Pending Conversions → Loop:
  ├─ Fetch Single Conversion from BigQuery
  ├─ Determine Click Identifier (GCLID/GBRAID/WBRAID)
  ├─ Build Conversion Payload
  ├─ Upload to Google Ads API
  ├─ Update BigQuery Response Column
  └─ Continue until no more pending conversions
→ Create Asana Task with Summary
```

### Key Characteristics
- **One-by-one processing:** Fetches and processes conversions individually
- **First-click attribution:** No external attribution data
- **Enhanced conversions:** Supports hashed email/phone for better matching
- **Response tracking:** Updates BigQuery table with API responses
- **Error resilience:** Continues processing even if individual conversions fail

---

## File Structure

```
google-ads-secondary-conversion_function-source/
├── main.py                    # Entry point, orchestration logic
├── bigquery_helper.py         # BigQuery operations (fetch, update)
├── google_ads_helper.py       # Google Ads API operations
├── secrets_manager.py         # GCP Secret Manager integration
├── asana_service.py           # Asana task creation
├── logger.py                  # Structured logging utility
├── requirements.txt           # Python dependencies
├── Procfile                   # Deployment configuration
└── venv/                      # Virtual environment (not included)
```

---

## Dependencies

### requirements.txt
```
functions-framework
google-ads==26.0.1
google-cloud-bigquery
google-cloud-secret-manager
python-dateutil
requests
pytz
python-dotenv
```

### Key Libraries
- **functions-framework:** Google Cloud Functions runtime
- **google-ads:** Google Ads API client library (v26.0.1)
- **google-cloud-bigquery:** BigQuery client
- **google-cloud-secret-manager:** Secure credential storage
- **python-dateutil:** Date/time parsing
- **requests:** HTTP requests (for Asana API)
- **pytz:** Timezone handling

---

## Detailed File Documentation

### 1. main.py

**Purpose:** Main entry point and orchestration logic

**Key Functions:**

#### `upload_conversions(request)`
- **Type:** HTTP Cloud Function entry point
- **Decorator:** `@functions_framework.http`
- **Flow:**
  1. Initialize BigQuery client
  2. Check for pending conversions (`get_required_runs_count`)
  3. If no pending conversions, return early
  4. Otherwise, call `upload_gads_conversions`

#### `upload_gads_conversions(request)`
- **Purpose:** Main processing loop
- **Metrics Tracked:**
  - `run_id`: Unique UUID for this execution
  - `total_conversions`: Total processed
  - `successful`: Successfully uploaded
  - `failed`: Failed uploads
  - `failed_by_reason`: Error breakdown by category
  - `processing_time_seconds`: Total execution time

**Processing Loop:**
```python
while True:
    1. Fetch single conversion from BigQuery view
    2. If no conversion found → break
    3. Determine click identifier (GCLID/GBRAID/WBRAID)
    4. Build conversion payload
    5. Upload to Google Ads API
    6. Check response for failures
    7. Update BigQuery with response
    8. Track metrics
```

**Error Handling:**
- **Validation errors:** Caught and logged, conversion marked as failed
- **API errors:** Caught and logged, conversion marked as failed
- **BigQuery update failures:** Critical - stops pipeline to prevent infinite loop
- **All errors:** Stored in BigQuery `response` column as string

**Response Format:**
```json
{
  "run_id": "uuid",
  "processed": 1500,
  "successful": 1498,
  "failed": 2,
  "failed_by_reason": {
    "Error message": 2
  },
  "processing_time_seconds": 45.23,
  "asana_task_created": true,
  "results": [...]
}
```

**Environment Variables Required:**
- `GCP_PROJECT_ID`
- `BIGQUERY_DATASET_ID`
- `BIGQUERY_COUNT_VIEW`
- `BIGQUERY_FETCH_VIEW`
- `BIGQUERY_CONVERSION_TABLE`
- `SERVICE_ACCOUNT_EMAIL`
- `ASANA_ACCESS_TOKEN` (optional)
- `ASANA_PROJECT_ID` (optional)

---

### 2. bigquery_helper.py

**Purpose:** BigQuery operations - fetching and updating conversion data

#### `get_required_runs_count(bq_client)`
- **Purpose:** Check how many conversions need processing
- **Query:** `SELECT * FROM {count_view}`
- **Returns:** Integer count of pending conversions
- **View Expected Schema:** Must have `runs_required` column

#### `fetch_single_conversion(bq_client)`
- **Purpose:** Fetch one pending conversion for processing
- **Query:** `SELECT * FROM {fetch_view}`
- **Returns:** Dictionary with conversion data or `None`
- **Expected Fields:**
  - `record_id`
  - `order_id`
  - `customer_id`
  - `conversion_value`
  - `order_timestamp_utc`
  - `email` (optional)
  - `phone` (optional)
  - `gclid` (optional)
  - `gbraid` (optional)
  - `wbraid` (optional)
  - `conversion_action_id`

**Logging:** Logs record_id, order_id, customer_id, conversion_value, and presence of email/phone

#### `update_conversion_response(bq_client, conversion, response_data)`
- **Purpose:** Update BigQuery table with API response
- **Update Query:**
  ```sql
  UPDATE {table}
  SET 
    response = @response_value,
    record_updated_at = CURRENT_TIMESTAMP()
  WHERE event_id = @event_id_value
  ```
- **Parameters:**
  - `response_value`: Stringified API response
  - `event_id_value`: Conversion's `order_id`
- **Returns:** `True` if successful, `False` if error
- **Critical:** If update fails, pipeline stops to prevent infinite loop

**Environment Variables:**
- `GCP_PROJECT_ID`
- `BIGQUERY_DATASET_ID`
- `BIGQUERY_COUNT_VIEW`
- `BIGQUERY_FETCH_VIEW`
- `BIGQUERY_CONVERSION_TABLE`

---

### 3. google_ads_helper.py

**Purpose:** Google Ads API operations and conversion payload building

#### `setup_google_ads_client()`
- **Purpose:** Initialize Google Ads API client
- **Process:**
  1. Fetch credentials from Secret Manager
  2. Create temporary YAML config file (`/tmp/google-ads.yaml`)
  3. Write service account key to `/tmp/service-account-key.json`
  4. Initialize client with API v19
- **Returns:** `GoogleAdsClient` instance

**YAML Config Structure:**
```yaml
developer_token: {from_secret}
login_customer_id: {from_secret}  # Optional
json_key_file_path: /tmp/service-account-key.json
impersonated_email: {SERVICE_ACCOUNT_EMAIL}
use_proto_plus: true
```

#### `determine_click_identifier(conversion)`
- **Purpose:** Determine which click ID to use (priority order)
- **Priority:**
  1. `gclid` (if present)
  2. `gbraid` (if present)
  3. `wbraid` (if present and not float/NaN)
- **Returns:** Tuple `(click_type, click_id)` or `(None, None)`
- **Note:** Returns first match found (priority order)

#### `format_timestamp(iso_timestamp)`
- **Purpose:** Format timestamp for Google Ads API
- **Input:** ISO timestamp string or datetime object
- **Output:** Formatted string `"YYYY-MM-DD HH:MM:SS+HH:MM"`
- **Handles:** Timezone-aware and timezone-naive timestamps

#### `format_phone_to_e164(phone_number)`
- **Purpose:** Format phone number to E.164 format
- **Logic:**
  - Removes non-digit characters
  - If 10 digits → adds `+1` prefix
  - If 11 digits starting with 1 → adds `+` prefix
  - Otherwise → adds `+` if missing
- **Returns:** E.164 formatted phone string

#### `normalize_and_hash(s)`
- **Purpose:** Normalize and SHA-256 hash string
- **Process:**
  1. Strip whitespace
  2. Convert to lowercase
  3. SHA-256 hash
- **Returns:** Hex digest string
- **Use:** For phone numbers and general hashing

#### `normalize_and_hash_email_address(email_address)`
- **Purpose:** Normalize and hash email (Google Ads specific)
- **Special Handling:**
  - Converts to lowercase
  - For Gmail/Googlemail domains: Removes dots before `@`
  - Example: `john.doe@gmail.com` → `johndoe@gmail.com`
- **Returns:** SHA-256 hashed email

#### `build_click_conversion(conversion, click_type, click_id)`
- **Purpose:** Build conversion payload for Google Ads API
- **Payload Structure:**
  ```python
  {
    "conversion_action": "customers/{customer_id}/conversionActions/{conversion_action_id}",
    "conversion_value": float,
    "conversion_date_time": "YYYY-MM-DD HH:MM:SS+HH:MM",
    "consent": {"ad_user_data": "GRANTED"},
    "gclid": "...",  # or gbraid/wbraid
    "order_id": "...",
    "user_identifiers": [  # Only if not gbraid/wbraid
      {
        "user_identifier_source": "FIRST_PARTY",
        "hashed_email": "..."
      },
      {
        "user_identifier_source": "FIRST_PARTY",
        "hashed_phone_number": "..."
      }
    ]
  }
  ```

**Enhanced Conversions Logic:**
- Only added if `click_type` is NOT `gbraid` or `wbraid`
- Email: Normalized and hashed
- Phone: Formatted to E.164, then hashed
- Both marked as `FIRST_PARTY` source

**Attribution:**
- **First-click attribution:** No `external_attribution_data` field
- Used for secondary conversions

#### `is_response_failure(response_str)`
- **Purpose:** Check if API response indicates failure
- **Logic:** Searches for empty `results {}` block in response string
- **Returns:** `True` if failure detected, `False` otherwise

#### `extract_error_category(response_str)`
- **Purpose:** Extract error message from API response
- **Logic:** Extracts `message` field from `partial_failure_error`
- **Returns:** Error message string or "Unknown Error"

#### `upload_click_conversion(google_ads_client, conversion, click_conversion)`
- **Purpose:** Upload conversion to Google Ads API
- **Service:** `ConversionUploadService`
- **Request:**
  ```python
  {
    "customer_id": conversion["customer_id"],
    "conversions": [click_conversion],
    "partial_failure": True,
    "debug_enabled": True
  }
  ```
- **Returns:** Stringified response (success) or exception (error)
- **Error Handling:** Catches `GoogleAdsException` and general exceptions

---

### 4. secrets_manager.py

**Purpose:** Secure credential retrieval from Google Cloud Secret Manager

#### `get_secret(secret_name, project_id=None)`
- **Purpose:** Fetch secret from Secret Manager
- **Process:**
  1. Uses `GCP_PROJECT_ID` if project_id not provided
  2. Constructs secret path: `projects/{project_id}/secrets/{secret_name}/versions/latest`
  3. Accesses secret version
  4. Decodes UTF-8
- **Returns:** Secret value as string
- **Logging:** Logs secret fetch (name only, not value)

#### `get_google_ads_credentials()`
- **Purpose:** Fetch all Google Ads credentials
- **Secrets Fetched:**
  - `puffy-mcc-google-ads-developer-token`
  - `puffy-mcc-google-ads-login-customer-id`
  - `puffy-mcc-google-ads-service-account-key`
- **Returns:** Dictionary with credentials
- **Structure:**
  ```python
  {
    "developer_token": "...",
    "login_customer_id": "...",
    "service_account_key": "..."  # JSON string
  }
  ```

---

### 5. asana_service.py

**Purpose:** Create Asana tasks for run summaries

#### `AsanaService` Class

**Initialization:**
- Reads `ASANA_ACCESS_TOKEN` and `ASANA_PROJECT_ID` from environment
- If missing, disables integration (graceful degradation)
- Logs initialization status

#### `_build_conversion_report(metrics, timestamp, duration)`
- **Purpose:** Build formatted text report
- **Sections:**
  1. Execution metadata (time, duration, run ID)
  2. Processing results (total, successful, failed, success rate)
  3. Error breakdown (by error message with counts and percentages)
  4. API response summary (if available)
  5. Performance metrics (total time, average per conversion)
- **Returns:** Formatted string

#### `create_conversion_task(metrics)`
- **Purpose:** Create Asana task with run summary
- **Process:**
  1. Gets current time in GST (Asia/Dubai timezone)
  2. Determines status prefix: `[SUCCESS]`, `[ERROR]`, or `[PARTIAL]`
  3. Builds task name: `{status} Google Ads Secondary Conversions (First Click) - {timestamp} - {successful}/{total} successful`
  4. Formats duration as `HH:MM:SS`
  5. Builds report using `_build_conversion_report`
  6. POSTs to Asana API
- **API Endpoint:** `https://app.asana.com/api/1.0/tasks`
- **Request:**
  ```json
  {
    "data": {
      "name": "Task name",
      "notes": "Report content",
      "projects": [project_id],
      "resource_subtype": "default_task"
    }
  }
  ```
- **Returns:** Task data dictionary or `None` if failed
- **Error Handling:** Catches all exceptions, logs but doesn't fail pipeline

**Environment Variables:**
- `ASANA_ACCESS_TOKEN` (optional)
- `ASANA_PROJECT_ID` (optional)

---

### 6. logger.py

**Purpose:** Structured logging utility with context support

#### `StructuredLogger` Class

**Features:**
- Module-based logging (separate logger per module)
- Structured context (JSON format)
- Automatic redaction of sensitive fields
- Standard Python logging levels

**Initialization:**
- Creates logger with module name
- Sets up console handler (stdout)
- Custom formatter: `[timestamp] [level] [module.function] message | context={json}`

#### `_format_context(context)`
- **Purpose:** Format context dictionary as JSON
- **Security:** Redacts fields containing: `token`, `key`, `password`, `secret`
- **Redaction:** Replaces value with `***REDACTED***`
- **Returns:** Formatted string or empty string

**Methods:**
- `debug(message, context=None)`
- `info(message, context=None)`
- `warning(message, context=None)`
- `error(message, context=None)`
- `critical(message, context=None)`

**Usage:**
```python
logger = get_logger("module_name")
logger.info("Processing conversion", {
    "order_id": "12345",
    "customer_id": "67890",
    "api_key": "secret"  # Will be redacted
})
```

---

### 7. Procfile

**Content:**
```
web: functions-framework --target=upload_conversions --port=$PORT
```

**Purpose:** Deployment configuration for Cloud Functions
- **Target:** `upload_conversions` function
- **Port:** Uses `$PORT` environment variable

---

## Data Flow

### Complete Pipeline Flow

```
1. HTTP Request Received
   ↓
2. Initialize BigQuery Client
   ↓
3. Check Pending Conversions (count_view)
   ├─ If count = 0 → Return early
   └─ If count > 0 → Continue
   ↓
4. Initialize Google Ads Client
   ├─ Fetch credentials from Secret Manager
   ├─ Create temp config files
   └─ Initialize API client
   ↓
5. Processing Loop (while True)
   ├─ Fetch Single Conversion (fetch_view)
   │  ├─ If None → Break loop
   │  └─ If Found → Continue
   │
   ├─ Determine Click Identifier
   │  ├─ Check gclid → Use if present
   │  ├─ Check gbraid → Use if present
   │  └─ Check wbraid → Use if present
   │
   ├─ Build Conversion Payload
   │  ├─ Format timestamp
   │  ├─ Add click identifier
   │  ├─ Add order_id
   │  └─ Add user identifiers (if not gbraid/wbraid)
   │     ├─ Hash email (Gmail normalization)
   │     └─ Format & hash phone (E.164)
   │
   ├─ Upload to Google Ads API
   │  ├─ Call ConversionUploadService
   │  ├─ Check response for failures
   │  └─ Track success/failure
   │
   └─ Update BigQuery
      ├─ Update response column
      ├─ Update record_updated_at
      └─ If update fails → Stop pipeline (critical)
   ↓
6. Create Asana Task
   ├─ Build summary report
   ├─ Create task in Asana project
   └─ Log task creation status
   ↓
7. Return JSON Response
```

### BigQuery Views Expected

#### Count View (`BIGQUERY_COUNT_VIEW`)
**Purpose:** Quick check for pending conversions
**Schema:**
- `runs_required` (INTEGER): Count of pending conversions

#### Fetch View (`BIGQUERY_FETCH_VIEW`)
**Purpose:** Fetch one pending conversion at a time
**Expected Schema:**
- `record_id` (STRING)
- `order_id` (STRING) - Used as event_id for updates
- `customer_id` (STRING) - Google Ads customer ID
- `conversion_action_id` (STRING) - Conversion action ID
- `conversion_value` (FLOAT)
- `order_timestamp_utc` (TIMESTAMP) - ISO format
- `email` (STRING, nullable)
- `phone` (STRING, nullable)
- `gclid` (STRING, nullable)
- `gbraid` (STRING, nullable)
- `wbraid` (STRING, nullable)

**View Logic:** Should return only ONE row (LIMIT 1) and filter for pending conversions

#### Conversion Table (`BIGQUERY_CONVERSION_TABLE`)
**Purpose:** Source table that gets updated
**Update Query:**
```sql
UPDATE {table}
SET 
  response = @response_value,
  record_updated_at = CURRENT_TIMESTAMP()
WHERE event_id = @event_id_value
```

**Expected Columns:**
- `event_id` (STRING) - Primary key, matches `order_id`
- `response` (STRING) - Stores API response
- `record_updated_at` (TIMESTAMP) - Last update time

---

## Key Implementation Details

### Click Identifier Priority
1. **GCLID** (Google Click ID) - Highest priority
2. **GBRAID** (Google Browser ID) - Second priority
3. **WBRAID** (Web Browser ID) - Third priority (only if not float/NaN)

### Enhanced Conversions
- **When Used:** Only if click identifier is NOT `gbraid` or `wbraid`
- **Email Processing:**
  - Lowercase conversion
  - Gmail/Googlemail: Remove dots before `@`
  - SHA-256 hash
- **Phone Processing:**
  - Extract digits only
  - Format to E.164
  - SHA-256 hash

### Attribution Model
- **Type:** First-click attribution
- **Implementation:** No `external_attribution_data` field in payload
- **Use Case:** Secondary conversions (offline conversions)

### Error Handling Strategy
1. **Validation Errors:** Logged, conversion marked failed, continue processing
2. **API Errors:** Logged, conversion marked failed, continue processing
3. **BigQuery Update Failures:** **CRITICAL** - Stops pipeline to prevent infinite loop
4. **All Errors:** Stored in BigQuery `response` column as string

### Response Tracking
- **Success:** Response string stored in BigQuery
- **Failure:** Error message stored in BigQuery
- **Format:** Stringified API response or exception message
- **Purpose:** Audit trail and debugging

### Metrics Collection
- **Per Conversion:**
  - Success/failure status
  - Error category (if failed)
- **Per Run:**
  - Total conversions processed
  - Successful count
  - Failed count
  - Failed by reason (dictionary)
  - Processing time (seconds)
  - Run ID (UUID)

---

## Error Handling

### Error Categories

1. **Validation Errors (`ValueError`)**
   - Caught in try/except
   - Logged with order_id context
   - Conversion marked as failed
   - Error stored in BigQuery
   - Pipeline continues

2. **Google Ads API Errors (`GoogleAdsException`)**
   - Caught in `upload_click_conversion`
   - Stringified and returned
   - Checked via `is_response_failure`
   - Error category extracted via `extract_error_category`
   - Conversion marked as failed
   - Pipeline continues

3. **General Exceptions**
   - Caught in multiple places
   - Logged with error type and message
   - Conversion marked as failed
   - Error stored in BigQuery
   - Pipeline continues (unless BigQuery update fails)

4. **BigQuery Update Failures**
   - **CRITICAL ERROR**
   - Logged as critical
   - Pipeline **STOPS** immediately
   - Prevents infinite loop (same conversion processed repeatedly)

### Error Response Format

**In BigQuery `response` column:**
- Success: Stringified API response
- Failure: Error message string (truncated to 200 chars for metrics)

**In Metrics:**
```python
{
  "failed_by_reason": {
    "Error message 1": 5,
    "Error message 2": 2
  }
}
```

---

## Integration Points

### Google Cloud Functions
- **Trigger:** HTTP
- **Entry Point:** `upload_conversions(request)`
- **Runtime:** Python 3.x
- **Deployment:** Via Procfile

### Google Cloud Secret Manager
- **Secrets Used:**
  - `puffy-mcc-google-ads-developer-token`
  - `puffy-mcc-google-ads-login-customer-id`
  - `puffy-mcc-google-ads-service-account-key`
- **Access:** Via service account (default credentials)

### Google BigQuery
- **Operations:**
  - Read from views (count, fetch)
  - Update table (response column)
- **Views Required:**
  - Count view (pending conversions count)
  - Fetch view (single pending conversion)
- **Table Required:**
  - Conversion table (with `event_id`, `response`, `record_updated_at`)

### Google Ads API
- **Version:** v19
- **Service:** ConversionUploadService
- **Method:** `upload_click_conversions`
- **Features:**
  - Partial failure enabled
  - Debug enabled
  - Enhanced conversions support

### Asana API
- **Endpoint:** `https://app.asana.com/api/1.0/tasks`
- **Method:** POST
- **Authentication:** Bearer token
- **Purpose:** Run summary task creation
- **Optional:** Pipeline continues if Asana fails

---

## Environment Variables Summary

### Required
- `GCP_PROJECT_ID` - GCP project ID
- `BIGQUERY_DATASET_ID` - BigQuery dataset ID
- `BIGQUERY_COUNT_VIEW` - View name for count check
- `BIGQUERY_FETCH_VIEW` - View name for fetching conversions
- `BIGQUERY_CONVERSION_TABLE` - Table name for updates
- `SERVICE_ACCOUNT_EMAIL` - Service account email for impersonation

### Optional
- `ASANA_ACCESS_TOKEN` - Asana API token
- `ASANA_PROJECT_ID` - Asana project ID
- `PORT` - Server port (for Cloud Functions)

---

## Key Learnings for Metricate MVP

### What to Replicate
1. ✅ **One-by-one processing** - Process conversions individually
2. ✅ **Click ID priority logic** - GCLID → GBRAID → WBRAID
3. ✅ **Enhanced conversions** - Email/phone hashing and normalization
4. ✅ **Response tracking** - Store API responses in BigQuery
5. ✅ **Error categorization** - Track failures by reason
6. ✅ **Metrics collection** - Track success/failure counts

### What to Adapt
1. 🔄 **Credentials storage** - Use PostgreSQL (encrypted) instead of Secret Manager
2. 🔄 **Scheduling** - Use Bull queue instead of HTTP trigger
3. 🔄 **Multi-tenancy** - Support multiple users/accounts
4. 🔄 **Field mappings** - Make configurable per sync
5. 🔄 **Query flexibility** - Support SQL queries or table names
6. 🔄 **Logging** - Store in PostgreSQL `sync_runs` table

### What to Skip (for MVP)
1. ❌ **Asana integration** - Not needed for MVP
2. ❌ **BigQuery views** - Client handles their own views
3. ❌ **Secret Manager** - Use PostgreSQL encryption
4. ❌ **Cloud Functions** - Use Bull workers instead

---

## Code Patterns to Reuse

### Click Identifier Determination
```python
def determine_click_identifier(conversion):
    if conversion.get("gclid"):
        return "gclid", conversion["gclid"]
    elif conversion.get("gbraid"):
        return "gbraid", conversion["gbraid"]
    elif conversion.get("wbraid") and not isinstance(conversion["wbraid"], float):
        return "wbraid", conversion["wbraid"]
    return None, None
```

### Email Hashing (Gmail Normalization)
```python
def normalize_and_hash_email_address(email_address):
    normalized_email = email_address.lower()
    email_parts = normalized_email.split("@")
    is_gmail = re.match(r"^(gmail|googlemail)\.com$", email_parts[1])
    
    if len(email_parts) > 1 and is_gmail:
        email_parts[0] = email_parts[0].replace(".", "")
        normalized_email = "@".join(email_parts)
    
    return hashlib.sha256(normalized_email.encode()).hexdigest()
```

### Phone Formatting (E.164)
```python
def format_phone_to_e164(phone_number):
    digits_only = ''.join(filter(str.isdigit, str(phone_number)))
    
    if len(digits_only) == 10:
        return f"+1{digits_only}"
    elif len(digits_only) == 11 and digits_only.startswith('1'):
        return f"+{digits_only}"
    else:
        return f"+{digits_only}" if not digits_only.startswith('+') else digits_only
```

### Conversion Payload Building
```python
click_conversion = {
    "conversion_action": f"customers/{customer_id}/conversionActions/{conversion_action_id}",
    "conversion_value": float(conversion_value),
    "conversion_date_time": formatted_timestamp,
    "consent": {"ad_user_data": "GRANTED"},
    click_type: click_id,  # gclid, gbraid, or wbraid
    "order_id": order_id,
    "user_identifiers": [...]  # Only if not gbraid/wbraid
}
```

---

## Testing Considerations

### Unit Tests Needed
- Click identifier priority logic
- Email normalization (especially Gmail)
- Phone formatting (E.164)
- Timestamp formatting
- Error response parsing

### Integration Tests Needed
- BigQuery connection and queries
- Google Ads API upload
- Error handling scenarios
- BigQuery update failures

### Edge Cases to Handle
- Missing click identifiers
- Invalid email formats
- Invalid phone formats
- Missing conversion values
- API rate limits
- Network timeouts

---

## Performance Considerations

### Current Implementation
- **Processing:** Sequential (one conversion at a time)
- **API Calls:** One per conversion
- **BigQuery Updates:** One per conversion
- **Throughput:** Limited by API rate limits

### Optimization Opportunities
- Batch API uploads (if Google Ads supports)
- Batch BigQuery updates
- Parallel processing (multiple workers)
- Caching credentials

---

## Security Considerations

### Credentials
- Stored in Secret Manager (encrypted at rest)
- Never logged (redacted in logs)
- Temporary files cleaned up

### Data Privacy
- Email/phone hashed before sending
- No PII stored in logs
- Sensitive fields redacted

### Access Control
- Service account with minimal permissions
- BigQuery: Read from views, update specific table
- Google Ads: Conversion upload only

---

## Monitoring and Alerting

### Current Monitoring
- Structured logs with context
- Asana task creation (run summaries)
- BigQuery response tracking

### Recommended Additions
- Error rate alerts
- Processing time alerts
- Failed conversion alerts
- API quota monitoring

---

## Deployment Notes

### Cloud Functions Deployment
- Uses Procfile for configuration
- Requires environment variables
- Uses default service account
- Needs Secret Manager access

### Dependencies
- All Python packages in `requirements.txt`
- Google Cloud SDK
- Functions Framework

---

## Conclusion

This pipeline demonstrates a production-ready implementation of a reverse ETL system for Google Ads offline conversions. Key aspects include:

1. **Robust error handling** - Continues processing despite individual failures
2. **Comprehensive logging** - Structured logs with context
3. **Response tracking** - All API responses stored in BigQuery
4. **Enhanced conversions** - Proper email/phone hashing and normalization
5. **Click identifier handling** - Priority-based selection
6. **Metrics collection** - Detailed success/failure tracking

For Metricate MVP, adapt this pattern to:
- Use PostgreSQL for configuration and logs
- Use Bull for job scheduling
- Support multiple users/accounts
- Make field mappings configurable
- Support flexible query options

---

**End of Documentation**
