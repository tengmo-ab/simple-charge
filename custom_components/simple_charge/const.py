"""Constants for Simple Charge."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "simple_charge"
NAME: Final = "Simple Charge"

# Config entry options -------------------------------------------------------
CONF_NAME: Final = "name"
CONF_PRICE_ENTITIES: Final = "price_entities"
CONF_FORECAST_ENTITIES: Final = "forecast_entities"
CONF_REFERENCE_ENTITY: Final = "reference_entity"
CONF_NORDPOOL_AREA: Final = "nordpool_area"

CONF_CONTROL_TYPE: Final = "control_type"
CONF_SWITCH_ENTITY: Final = "switch_entity"
CONF_SELECT_ENTITY: Final = "select_entity"
CONF_SELECT_ON: Final = "select_on_option"
CONF_SELECT_OFF: Final = "select_off_option"
CONF_START_SCRIPT: Final = "start_script"
CONF_STOP_SCRIPT: Final = "stop_script"
CONF_LIMITER_SWITCH: Final = "limiter_switch"

CONF_HYSTERESIS: Final = "hysteresis_pct"
CONF_FORECAST_MARGIN: Final = "forecast_margin_pct"
CONF_MAX_WAIT_HOURS: Final = "max_wait_hours"
CONF_REFERENCE_DAYS: Final = "reference_days"

CONF_SOC_ENTITY: Final = "soc_entity"
CONF_BATTERY_KWH: Final = "battery_kwh"
CONF_CHARGER_KW: Final = "charger_kw"
CONF_EFFICIENCY: Final = "efficiency_pct"

CONF_GARO_SCHEDULE_ENTITY: Final = "garo_schedule_entity"
CONF_GARO_CHARGE_LIMIT: Final = "garo_charge_limit"

CONTROL_NONE: Final = "none"
CONTROL_SWITCH: Final = "switch"
CONTROL_SELECT: Final = "select"
CONTROL_SCRIPT: Final = "script"
CONTROL_TYPES: Final = [CONTROL_NONE, CONTROL_SWITCH, CONTROL_SELECT, CONTROL_SCRIPT]

DEFAULT_HYSTERESIS: Final = 15.0
DEFAULT_FORECAST_MARGIN: Final = 15.0
DEFAULT_MAX_WAIT_HOURS: Final = 72.0
DEFAULT_REFERENCE_DAYS: Final = 7
DEFAULT_EFFICIENCY: Final = 90.0
DEFAULT_GARO_CHARGE_LIMIT: Final = 16

# Runtime settings (changed through the integration's own entities) ---------
SET_MODE: Final = "mode"
SET_CHARGER_CONTROL: Final = "charger_control"
SET_DURATION_HOURS: Final = "duration_hours"
SET_MAX_PRICE: Final = "max_price"
SET_RELATIVE_LIMIT: Final = "relative_limit_pct"
SET_USE_FORECAST: Final = "use_forecast"
SET_DEADLINE_ENABLED: Final = "deadline_enabled"
SET_DEADLINE: Final = "deadline"
SET_WINDOW_START: Final = "force_window_start"
SET_WINDOW_END: Final = "force_window_end"
SET_TARGET_SOC: Final = "target_soc"
SET_GARO_SYNC: Final = "garo_schedule_sync"

MODE_SMART: Final = "smart"
MODE_FORCE: Final = "force"
MODE_PAUSED: Final = "paused"
MODES: Final = [MODE_SMART, MODE_FORCE, MODE_PAUSED]

DEFAULT_SETTINGS: Final = {
    SET_MODE: MODE_SMART,
    SET_CHARGER_CONTROL: True,
    SET_DURATION_HOURS: 2.0,
    SET_MAX_PRICE: 0.0,  # 0 = no fixed cap
    SET_RELATIVE_LIMIT: 0.0,  # 0 = no relative cap
    SET_USE_FORECAST: True,
    SET_DEADLINE_ENABLED: False,
    SET_DEADLINE: None,
    SET_WINDOW_START: None,
    SET_WINDOW_END: None,
    SET_TARGET_SOC: 80.0,
    SET_GARO_SYNC: False,
}

STORAGE_VERSION: Final = 1

SERVICE_FORCE_CHARGE: Final = "force_charge"
SERVICE_CLEAR_FORCE: Final = "clear_force"
ATTR_DURATION: Final = "duration"
ATTR_ENTRY_ID: Final = "config_entry_id"
