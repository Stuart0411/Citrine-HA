DOMAIN = "citrineos_load_management"
PLATFORMS = ["sensor"]

CONF_MODE = "mode"
MODE_BRIDGE = "bridge"
MODE_DIRECT = "direct"

CONF_BRIDGE_URL = "bridge_url"
CONF_SHARED_SECRET = "shared_secret"
CONF_POLL_SECONDS = "poll_seconds"
CONF_CITRINEOS_BASE_URL = "citrineos_base_url"
CONF_CITRINEOS_STATIONS_URL = "citrineos_stations_url"
CONF_MANUAL_STATIONS_JSON = "manual_stations_json"
CONF_CITRINEOS_OCPP2_PREFIX = "citrineos_ocpp2_prefix"
CONF_CITRINEOS_OCPP16_PREFIX = "citrineos_ocpp16_prefix"
CONF_STATION_DEFAULT_TENANT_ID = "station_default_tenant_id"
CONF_STATION_DEFAULT_PROTOCOL = "station_default_protocol"
CONF_STATION_DEFAULT_MAX_WATTS = "station_default_max_watts"
CONF_STATION_DEFAULT_WEIGHT = "station_default_weight"
CONF_CHARGERS = "chargers"
CONF_GROUPS = "groups"

DEFAULT_POLL_SECONDS = 30
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_CITRINEOS_OCPP2_PREFIX = "smartcharging"
DEFAULT_CITRINEOS_OCPP16_PREFIX = "smartcharging"
DEFAULT_STATION_DEFAULT_TENANT_ID = 1
DEFAULT_STATION_DEFAULT_PROTOCOL = "1.6"
DEFAULT_STATION_DEFAULT_MAX_WATTS = 11000
DEFAULT_STATION_DEFAULT_WEIGHT = 1
DEFAULT_CHARGERS: list[dict[str, object]] = []
DEFAULT_GROUPS: list[dict[str, object]] = []

SERVICE_APPLY_SITE_BUDGET = "apply_site_budget"
SERVICE_APPLY_DIRECT_LIMITS = "apply_direct_limits"
SERVICE_RECONCILE = "reconcile"
SERVICE_REMOTE_START_TRANSACTION = "remote_start_transaction"
SERVICE_REMOTE_STOP_TRANSACTION = "remote_stop_transaction"
SERVICE_SET_AVAILABILITY = "set_availability"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
