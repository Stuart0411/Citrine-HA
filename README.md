# CitrineOS + Home Assistant Load Management Bridge

This implementation is a starter module/service that:

- Accepts desired site load policy from Home Assistant via webhook/REST.
- Splits site budget across configured chargers with optional per-station overrides.
- Accepts direct per-station limits and per-group limits, then compiles them into per-charger commands.
- Translates limits into OCPP smart-charging SetChargingProfile commands for:
  - OCPP 2.0.1
  - OCPP 1.6
- Dispatches commands to CitrineOS message endpoints.
- Persists desired/effective state and command outbox.
- Applies a safe fallback cap if policy updates become stale.

## Quick start

1. Install dependencies:

```powershell
npm install
```

2. Create env file:

```powershell
Copy-Item .\.env.example .\.env
```

3. Set `CITRINEOS_STATIONS_URL` in `.env` to your CitrineOS station inventory endpoint.

4. Start service:

```powershell
npm run dev
```

On startup, the bridge fetches station data from CitrineOS and writes `config/stations.json` automatically.
If discovery fails or returns no stations, it falls back to local `config/stations.json` (or `config/stations.example.json`).

## Docker

Build and run with Docker Compose:

```powershell
Copy-Item .\.env.example .\.env
docker compose up --build -d
```

Check status and health:

```powershell
docker compose ps
```

Stop the container:

```powershell
docker compose down
```

Notes:

- `./config` is mounted to `/app/config` so discovered `stations.json` persists on host.
- `./data` is mounted to `/app/data` so runtime state/outbox persists on host.
- Service listens on `http://localhost:8095`.
- Container runs as non-root (`node` user) and includes a `/health` Docker healthcheck.
- Docker build/install uses `npm ci` automatically when `package-lock.json` is present, else falls back to `npm install`.

Optional development container (hot reload):

```powershell
docker compose --profile dev up bridge-dev
```

The dev service listens on `http://localhost:8096`.

Build/run without Compose:

```powershell
docker build -t citrineos-ha-load-management .
docker run --rm -p 8095:8095 --env-file .env -v ${PWD}/config:/app/config -v ${PWD}/data:/app/data citrineos-ha-load-management
```

For reproducible builds, generate and commit `package-lock.json`.

## API

### Health

- `GET /health`

### Stations

- `GET /api/v1/stations`

### Submit policy (Home Assistant webhook target)

- `POST /api/v1/policies/site-budget`
- Header: `x-shared-secret: <WEBHOOK_SHARED_SECRET>`

Body:

```json
{
  "idempotencyKey": "202605181530",
  "sourceTimestamp": "2026-05-18T15:30:00.000Z",
  "ttlSeconds": 120,
  "siteBudgetWatts": 16000,
  "stationOverrides": [
    {
      "stationId": "CS-2001",
      "maxWatts": 9000
    }
  ]
}
```

### Submit direct station/group limits

- `POST /api/v1/policies/direct-limits`
- Header: `x-shared-secret: <WEBHOOK_SHARED_SECRET>`

Body:

```json
{
  "mode": "direct-limits",
  "idempotencyKey": "202605191030",
  "sourceTimestamp": "2026-05-19T10:30:00.000Z",
  "ttlSeconds": 120,
  "stationLimits": [
    {
      "stationId": "CS-2001",
      "maxWatts": 9000
    }
  ],
  "groups": [
    {
      "groupId": "parking-east",
      "stationIds": ["CS-2001", "CS-1601"]
    }
  ],
  "groupLimits": [
    {
      "groupId": "parking-east",
      "maxWatts": 12000
    }
  ],
  "defaultUnspecifiedWatts": 6000
}
```

Group limits are split across group members using station weight and station max caps. If a station appears in multiple group limits, the most restrictive result is used. Explicit `stationLimits` then override the group-derived value for that station.

### Trigger reconciliation

- `POST /api/v1/policies/reconcile`
- Header: `x-shared-secret: <WEBHOOK_SHARED_SECRET>`

### Remote start transaction

- `POST /api/v1/operations/remote-start`
- Header: `x-shared-secret: <WEBHOOK_SHARED_SECRET>`

Body:

```json
{
  "stationId": "CS-2001",
  "idToken": "HA-RFID-001",
  "evseId": 1,
  "connectorId": 1
}
```

Behavior:

- The integration now auto-generates an incrementing transaction id each time remote start is called.
- For OCPP 2.0.1, this value is also used as `remoteStartId` when not explicitly provided.
- The generated `transactionId` is returned in the API response and can be used for remote stop.

### Remote stop transaction

- `POST /api/v1/operations/remote-stop`
- Header: `x-shared-secret: <WEBHOOK_SHARED_SECRET>`

Body:

```json
{
  "stationId": "CS-2001",
  "transactionId": "12345"
}
```

`transactionId` is optional. If omitted, the most recently auto-generated transaction id for the station is used.

### Set charger availability

- `POST /api/v1/operations/set-availability`
- Header: `x-shared-secret: <WEBHOOK_SHARED_SECRET>`

Body:

```json
{
  "stationId": "CS-2001",
  "operationalStatus": "Inoperative",
  "evseId": 1,
  "connectorId": 1
}
```

### Inspect state and outbox

- `GET /api/v1/state`

## Home Assistant wiring

Use the example in `home-assistant/automation-example.yaml`.

## HACS integration

This repository now includes a HACS custom integration at `custom_components/citrineos_load_management`.

Install steps:

1. In HACS, add this repository as a custom repository with category `Integration`.
2. Install `CitrineOS Load Management` from HACS.
3. Restart Home Assistant.
4. Add integration: `Settings -> Devices & Services -> Add Integration -> CitrineOS Load Management`.
5. Select mode:
  - `Direct` (recommended): Home Assistant talks to CitrineOS directly and runs policy handling internally.
  - `Bridge`: Home Assistant calls this repository's Node bridge service.
6. Configure selected mode:
  - Direct mode:
    - CitrineOS base URL (for example, `http://YOUR_CITRINEOS_HOST:8080`)
    - Optional station inventory URL (defaults to `/api/v1/charging-stations`)
    - Optional manual stations JSON fallback (used when no station inventory endpoint exists)
    - OCPP module prefixes and station defaults
    - Poll interval
  - Bridge mode:
    - Bridge URL (for example, `http://YOUR_BRIDGE_HOST:8095`)
    - Webhook shared secret (same value as bridge `WEBHOOK_SHARED_SECRET`)
    - Poll interval

What it provides:

- Auto-discovered station sensors from bridge station inventory.
- Auto-discovered per-station button entities:
  - `<station> Remote Start`
  - `<station> Set Operative`
  - `<station> Set Inoperative`
- Service calls for load policy control:
  - `citrineos_load_management.apply_site_budget`
  - `citrineos_load_management.apply_direct_limits`
  - `citrineos_load_management.remote_start_transaction`
  - `citrineos_load_management.remote_stop_transaction`
  - `citrineos_load_management.set_availability`
  - `citrineos_load_management.reconcile`

## Phase 1: Home Assistant-first configuration UI

The integration options flow now includes a native management menu focused on Home Assistant as the primary control surface:

- `Connection settings`
- `Add charger`
- `Edit charger`
- `Delete charger`
- `Add group`
- `Edit group`
- `Delete group`
- `Save and close`

Charger fields include station id, protocol, tenant id, max watts, weight, and optional EVSE/connector ids.
Group fields include group id, member station ids, and optional max watts.

For direct mode, configured chargers/groups are used as the primary station inventory source before manual JSON/discovery routes.

Service notes:

- If multiple integration instances are configured, provide `config_entry_id` in service data.
- Grouping behavior is policy-layer grouping compiled to per-station commands before dispatch.
- Per-station `Remote Start` button uses deterministic id token `HA-<stationId>`.
- Remote stop remains a service call because it requires a transaction id.

## Home Assistant dashboard package

This repository includes a ready-to-import package and Lovelace dashboard YAML:

- `home-assistant/packages/citrineos_load_management_package.yaml`
- `home-assistant/lovelace/citrineos_load_management_dashboard.yaml`

Package includes:

- Input helpers for station id, id token, transaction id, availability, and budget/limit values.
- Scripts that call HACS integration services for:
  - Site budget apply
  - Direct station/group limits
  - Remote transaction start/stop
  - Set availability

Dashboard includes:

- Fleet status cards.
- Operator input controls.
- One-tap action buttons for all core operations.

Install package and dashboard:

1. Ensure Home Assistant `packages:` is enabled in `configuration.yaml`.
2. Copy `home-assistant/packages/citrineos_load_management_package.yaml` into your HA packages directory.
3. Add or import `home-assistant/lovelace/citrineos_load_management_dashboard.yaml` in Lovelace dashboard settings.
4. Restart Home Assistant.

## Important notes

- Endpoint path assumptions for CitrineOS are based on current module routing behavior.
- In this bridge, grouping is handled in policy compilation, not as a native grouped smart-charging command. Commands sent to CitrineOS are still per charging station (`SetChargingProfile`).
- Station discovery requires `CITRINEOS_STATIONS_URL` and expects JSON array payloads (or `{ stations: [] }`, `{ data: [] }`, `{ results: [] }`).
- When station fields are missing from CitrineOS records, safe defaults are applied via env vars:
  - `STATION_DEFAULT_TENANT_ID`
  - `STATION_DEFAULT_PROTOCOL`
  - `STATION_DEFAULT_MAX_WATTS`
  - `STATION_DEFAULT_WEIGHT`
- Adjust endpoint prefixes (`CITRINEOS_OCPP2_PREFIX`, `CITRINEOS_OCPP16_PREFIX`) to your CitrineOS config.
- This is phase-1 implementation scaffolding and keeps persistence in `data/state.json`.
- For production, migrate state/outbox to PostgreSQL and add signed webhook payload verification.
