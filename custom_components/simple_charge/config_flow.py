"""UI setup for Simple Charge.

Four short steps, the same in setup and in Options:
prices -> charger -> charger details -> advanced (all optional).
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector as sel
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
    CONF_BATTERY_KWH,
    CONF_CHARGER_KW,
    CONF_CONTROL_TYPE,
    CONF_EFFICIENCY,
    CONF_FORECAST_ENTITIES,
    CONF_FORECAST_MARGIN,
    CONF_GARO_CHARGE_LIMIT,
    CONF_GARO_SCHEDULE_ENTITY,
    CONF_HYSTERESIS,
    CONF_LIMITER_SWITCH,
    CONF_MAX_WAIT_HOURS,
    CONF_NAME,
    CONF_NORDPOOL_AREA,
    CONF_PRICE_ENTITIES,
    CONF_REFERENCE_DAYS,
    CONF_REFERENCE_ENTITY,
    CONF_SELECT_ENTITY,
    CONF_SELECT_OFF,
    CONF_SELECT_ON,
    CONF_SOC_ENTITY,
    CONF_START_SCRIPT,
    CONF_STOP_SCRIPT,
    CONF_SWITCH_ENTITY,
    CONTROL_NONE,
    CONTROL_SCRIPT,
    CONTROL_SELECT,
    CONTROL_SWITCH,
    CONTROL_TYPES,
    DEFAULT_EFFICIENCY,
    DEFAULT_FORECAST_MARGIN,
    DEFAULT_GARO_CHARGE_LIMIT,
    DEFAULT_HYSTERESIS,
    DEFAULT_MAX_WAIT_HOURS,
    DEFAULT_REFERENCE_DAYS,
    DOMAIN,
    NAME,
)
from .prices import slots_from_attributes

CHARGER_KEYS = (
    CONF_SWITCH_ENTITY,
    CONF_SELECT_ENTITY,
    CONF_SELECT_ON,
    CONF_SELECT_OFF,
    CONF_START_SCRIPT,
    CONF_STOP_SCRIPT,
    CONF_LIMITER_SWITCH,
)
OPTIONAL_PRICE_KEYS = (CONF_FORECAST_ENTITIES, CONF_REFERENCE_ENTITY)
OPTIONAL_ADVANCED_KEYS = (
    CONF_SOC_ENTITY,
    CONF_BATTERY_KWH,
    CONF_CHARGER_KW,
    CONF_GARO_SCHEDULE_ENTITY,
    CONF_NORDPOOL_AREA,
)


def _entity(domain: str | list[str], multiple: bool = False, integration: str | None = None):
    config = sel.EntitySelectorConfig(domain=domain, multiple=multiple)
    if integration:
        config = sel.EntitySelectorConfig(domain=domain, multiple=multiple, integration=integration)
    return sel.EntitySelector(config)


def _number(minimum: float, maximum: float, step: float, unit: str | None = None):
    return sel.NumberSelector(
        sel.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=sel.NumberSelectorMode.BOX,
        )
    )


def _suggest(data: dict[str, Any], key: str) -> dict[str, Any]:
    return {"suggested_value": data.get(key)} if data.get(key) not in (None, "", []) else {}


class _Steps:
    """Steps shared by the config flow and the options flow."""

    _data: dict[str, Any]

    def _has_prices(self, entity_ids: list[str]) -> bool:
        tz = dt_util.get_default_time_zone()
        registry = er.async_get(self.hass)  # type: ignore[attr-defined]
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)  # type: ignore[attr-defined]
            if state is not None and slots_from_attributes(state.attributes, tz):
                return True
            entry = registry.async_get(entity_id)
            if entry is not None and entry.platform == "nordpool":
                return True
        return False

    async def async_step_prices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not self._has_prices(user_input.get(CONF_PRICE_ENTITIES, [])):
                errors[CONF_PRICE_ENTITIES] = "no_prices"
            else:
                for key in OPTIONAL_PRICE_KEYS:
                    if not user_input.get(key):
                        self._data.pop(key, None)
                self._data.update(user_input)
                return await self.async_step_charger()

        data = {**self._data, **(user_input or {})}
        schema: dict[Any, Any] = {}
        if isinstance(self, ConfigFlow):
            schema[vol.Required(CONF_NAME, default=data.get(CONF_NAME, NAME))] = str
        schema.update(
            {
                vol.Required(CONF_PRICE_ENTITIES, default=data.get(CONF_PRICE_ENTITIES, [])): _entity("sensor", multiple=True),
                vol.Optional(CONF_FORECAST_ENTITIES, description=_suggest(data, CONF_FORECAST_ENTITIES)): _entity(
                    "sensor", multiple=True
                ),
                vol.Optional(CONF_REFERENCE_ENTITY, description=_suggest(data, CONF_REFERENCE_ENTITY)): _entity(
                    ["sensor", "input_number"]
                ),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="prices", data_schema=vol.Schema(schema), errors=errors
        )

    async def async_step_charger(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            if user_input[CONF_CONTROL_TYPE] != self._data.get(CONF_CONTROL_TYPE):
                for key in CHARGER_KEYS:
                    if key != CONF_LIMITER_SWITCH:
                        self._data.pop(key, None)
            self._data.update(user_input)
            if user_input[CONF_CONTROL_TYPE] == CONTROL_NONE:
                return await self.async_step_advanced()
            return await self.async_step_charger_details()

        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="charger",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONTROL_TYPE, default=self._data.get(CONF_CONTROL_TYPE, CONTROL_SELECT)
                    ): sel.SelectSelector(
                        sel.SelectSelectorConfig(
                            options=CONTROL_TYPES,
                            translation_key=CONF_CONTROL_TYPE,
                            mode=sel.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_charger_details(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        control = self._data[CONF_CONTROL_TYPE]
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_LIMITER_SWITCH):
                self._data.pop(CONF_LIMITER_SWITCH, None)
            if control == CONTROL_SCRIPT and not (user_input.get(CONF_START_SCRIPT) or user_input.get(CONF_STOP_SCRIPT)):
                errors["base"] = "script_required"
            else:
                for key in (CONF_START_SCRIPT, CONF_STOP_SCRIPT):
                    if control == CONTROL_SCRIPT and not user_input.get(key):
                        self._data.pop(key, None)
                self._data.update(user_input)
                if control == CONTROL_SELECT:
                    return await self.async_step_select_options()
                return await self.async_step_advanced()

        data = self._data
        schema: dict[Any, Any] = {}
        if control == CONTROL_SWITCH:
            schema[vol.Required(CONF_SWITCH_ENTITY, default=data.get(CONF_SWITCH_ENTITY))] = _entity(["switch", "input_boolean"])
        elif control == CONTROL_SELECT:
            schema[vol.Required(CONF_SELECT_ENTITY, default=data.get(CONF_SELECT_ENTITY))] = _entity(["select", "input_select"])
        else:
            schema[vol.Optional(CONF_START_SCRIPT, description=_suggest(data, CONF_START_SCRIPT))] = _entity("script")
            schema[vol.Optional(CONF_STOP_SCRIPT, description=_suggest(data, CONF_STOP_SCRIPT))] = _entity("script")
        schema[vol.Optional(CONF_LIMITER_SWITCH, description=_suggest(data, CONF_LIMITER_SWITCH))] = _entity(
            ["switch", "input_boolean"]
        )
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="charger_details",
            data_schema=vol.Schema({k: v for k, v in schema.items() if v is not None}),
            errors=errors,
        )

    async def async_step_select_options(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_SELECT_ON] == user_input[CONF_SELECT_OFF]:
                errors["base"] = "same_option"
            else:
                self._data.update(user_input)
                return await self.async_step_advanced()

        state = self.hass.states.get(self._data[CONF_SELECT_ENTITY])  # type: ignore[attr-defined]
        options = list(state.attributes.get("options", [])) if state else []
        if not options:
            options = [o for o in (self._data.get(CONF_SELECT_ON), self._data.get(CONF_SELECT_OFF)) if o]

        def guess(words: tuple[str, ...]) -> str | None:
            for word in words:  # the first word that matches any option wins
                for option in options:
                    if word in option.lower():
                        return option
            return None

        default_on = self._data.get(CONF_SELECT_ON) or guess(("always_on", "on", "start", "charge"))
        default_off = self._data.get(CONF_SELECT_OFF) or guess(("schema", "schedule", "off", "stop"))

        def choice(default: str | None, key: str):
            if options:
                return (
                    vol.Required(key, default=default) if default in options else vol.Required(key),
                    sel.SelectSelector(sel.SelectSelectorConfig(options=options, custom_value=True)),
                )
            return (vol.Required(key, default=default or ""), str)

        on_key, on_sel = choice(default_on, CONF_SELECT_ON)
        off_key, off_sel = choice(default_off, CONF_SELECT_OFF)
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="select_options",
            data_schema=vol.Schema({on_key: on_sel, off_key: off_sel}),
            errors=errors,
        )

    async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            for key in OPTIONAL_ADVANCED_KEYS:
                if user_input.get(key) in (None, "", 0):
                    self._data.pop(key, None)
                    user_input.pop(key, None)
            self._data.update(user_input)
            return self._finish()

        data = self._data
        schema = {
            vol.Required(CONF_HYSTERESIS, default=data.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)): _number(0, 100, 1, "%"),
            vol.Required(CONF_FORECAST_MARGIN, default=data.get(CONF_FORECAST_MARGIN, DEFAULT_FORECAST_MARGIN)): _number(
                0, 100, 1, "%"
            ),
            vol.Required(CONF_MAX_WAIT_HOURS, default=data.get(CONF_MAX_WAIT_HOURS, DEFAULT_MAX_WAIT_HOURS)): _number(
                6, 336, 1, "h"
            ),
            vol.Required(CONF_REFERENCE_DAYS, default=data.get(CONF_REFERENCE_DAYS, DEFAULT_REFERENCE_DAYS)): _number(
                1, 30, 1, "d"
            ),
            vol.Optional(CONF_SOC_ENTITY, description=_suggest(data, CONF_SOC_ENTITY)): _entity(
                ["sensor", "input_number", "number"]
            ),
            vol.Optional(CONF_BATTERY_KWH, description=_suggest(data, CONF_BATTERY_KWH)): _number(0, 300, 0.1, "kWh"),
            vol.Optional(CONF_CHARGER_KW, description=_suggest(data, CONF_CHARGER_KW)): _number(0, 50, 0.1, "kW"),
            vol.Required(CONF_EFFICIENCY, default=data.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)): _number(50, 100, 1, "%"),
            vol.Optional(CONF_GARO_SCHEDULE_ENTITY, description=_suggest(data, CONF_GARO_SCHEDULE_ENTITY)): _entity(
                "sensor", integration="garo_wallbox"
            ),
            vol.Required(
                CONF_GARO_CHARGE_LIMIT,
                default=data.get(CONF_GARO_CHARGE_LIMIT, DEFAULT_GARO_CHARGE_LIMIT),
            ): _number(6, 32, 1, "A"),
            vol.Optional(CONF_NORDPOOL_AREA, description=_suggest(data, CONF_NORDPOOL_AREA)): str,
        }
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="advanced", data_schema=vol.Schema(schema)
        )

    def _finish(self) -> ConfigFlowResult:
        raise NotImplementedError


class SimpleChargeConfigFlow(_Steps, ConfigFlow, domain=DOMAIN):
    """Add a Simple Charge planner."""

    VERSION = 1

    def __init__(self) -> None:
        self._data = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self.async_step_prices(user_input)

    def _finish(self) -> ConfigFlowResult:
        name = self._data.pop(CONF_NAME, NAME)
        return self.async_create_entry(title=name, data={CONF_NAME: name}, options=self._data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SimpleChargeOptionsFlow()


class SimpleChargeOptionsFlow(_Steps, OptionsFlow):
    """Change any setup choice later."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._data = dict(self.config_entry.options)
        return await self.async_step_prices()

    def _finish(self) -> ConfigFlowResult:
        return self.async_create_entry(data=self._data)
