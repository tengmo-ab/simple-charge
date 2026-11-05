"""The coordinator: gathers prices, runs the planner and drives the charger."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .charger import ChargerController
from .const import (
    CONF_BATTERY_KWH,
    CONF_CHARGER_KW,
    CONF_EFFICIENCY,
    CONF_FORECAST_ENTITIES,
    CONF_FORECAST_MARGIN,
    CONF_GARO_CHARGE_LIMIT,
    CONF_GARO_SCHEDULE_ENTITY,
    CONF_HYSTERESIS,
    CONF_MAX_WAIT_HOURS,
    CONF_NORDPOOL_AREA,
    CONF_PRICE_ENTITIES,
    CONF_REFERENCE_DAYS,
    CONF_REFERENCE_ENTITY,
    CONF_SOC_ENTITY,
    DEADLINE_LIMITS,
    DEFAULT_EFFICIENCY,
    DEFAULT_FORECAST_MARGIN,
    DEFAULT_GARO_CHARGE_LIMIT,
    DEFAULT_HYSTERESIS,
    DEFAULT_MAX_WAIT_HOURS,
    DEFAULT_REFERENCE_DAYS,
    DEFAULT_SETTINGS,
    DOMAIN,
    MODE_FORCE,
    MODE_PAUSED,
    SET_CHARGER_CONTROL,
    SET_DEADLINE,
    SET_DEADLINE_ENABLED,
    SET_DEADLINE_MODE,
    SET_DURATION_HOURS,
    SET_GARO_SYNC,
    SET_MAX_PRICE,
    SET_MODE,
    SET_RELATIVE_LIMIT,
    SET_TARGET_SOC,
    SET_USE_FORECAST,
    SET_WINDOW_END,
    SET_WINDOW_START,
    STORAGE_VERSION,
)
from .garo_schedule import GaroScheduleSync
from .planner import (
    Plan,
    PlanInput,
    PriceSlot,
    Reason,
    make_plan,
    merge_ranges,
    needed_duration_from_soc,
)
from .prices import average, merge_slots, parse_list, slots_from_attributes

_LOGGER = logging.getLogger(__name__)

DATETIME_SETTINGS = (SET_DEADLINE, SET_WINDOW_START, SET_WINDOW_END)
NORDPOOL_REFRESH = timedelta(minutes=30)
GARO_SYNC_INTERVAL = timedelta(minutes=5)
MIN_SESSION_FOR_LAST_CHARGE = timedelta(minutes=14)

type SimpleChargeConfigEntry = ConfigEntry[SimpleChargeCoordinator]


class SimpleChargeCoordinator(DataUpdateCoordinator[Plan]):
    """Recalculates the plan every minute and whenever an input changes."""

    config_entry: SimpleChargeConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SimpleChargeConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=1),
            always_update=True,
        )
        self.options: dict[str, Any] = {**entry.data, **entry.options}
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.daily_averages: dict[str, float] = {}
        self.last_charge_end: datetime | None = None
        self._session_start: datetime | None = None
        self._last_charge_now: bool | None = None
        self._last_wanted: bool | None = None
        self._unsubs: list[Any] = []
        self._nordpool_cache: dict[date, list[PriceSlot]] = {}
        self._nordpool_fetched: dict[date, datetime] = {}
        self._garo_last_ranges: list[tuple[datetime, datetime]] | None = None
        self._garo_next_sync: datetime | None = None

        self.prices: list[PriceSlot] = []
        self.forecast: list[PriceSlot] = []
        self.reference_price: float | None = None
        self.duration: timedelta = timedelta()
        self.soc: float | None = None
        self.unit: str | None = None

        self.charger = ChargerController(hass, self.options, self._charger_changed)
        garo_entity = self.options.get(CONF_GARO_SCHEDULE_ENTITY)
        self.garo: GaroScheduleSync | None = (
            GaroScheduleSync(
                hass,
                garo_entity,
                int(self.options.get(CONF_GARO_CHARGE_LIMIT, DEFAULT_GARO_CHARGE_LIMIT)),
            )
            if garo_entity
            else None
        )

    # -- lifecycle -----------------------------------------------------------

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        for key, value in stored.get("settings", {}).items():
            if key in self.settings:
                if key in DATETIME_SETTINGS and value:
                    value = dt_util.parse_datetime(value)
                self.settings[key] = value
        self.daily_averages = dict(stored.get("daily_averages", {}))
        if stored.get("last_charge_end"):
            self.last_charge_end = dt_util.parse_datetime(stored["last_charge_end"])

    @callback
    def _data_to_store(self) -> dict[str, Any]:
        settings = {key: (value.isoformat() if isinstance(value, datetime) else value) for key, value in self.settings.items()}
        return {
            "settings": settings,
            "daily_averages": self.daily_averages,
            "last_charge_end": self.last_charge_end.isoformat() if self.last_charge_end else None,
        }

    def _save(self) -> None:
        self._store.async_delay_save(self._data_to_store, 5)

    @callback
    def async_start(self) -> None:
        watched = [
            *self.options.get(CONF_PRICE_ENTITIES, []),
            *self.options.get(CONF_FORECAST_ENTITIES, []),
        ]
        for key in (CONF_REFERENCE_ENTITY, CONF_SOC_ENTITY):
            if self.options.get(key):
                watched.append(self.options[key])
        if watched:
            self._unsubs.append(async_track_state_change_event(self.hass, watched, self._on_input_change))
        # Recalculate right at every quarter so slot changes are on time.
        self._unsubs.append(async_track_time_change(self.hass, self._on_quarter, minute=[0, 15, 30, 45], second=1))
        self.charger.async_start()

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self.charger.async_stop()
        await self._store.async_save(self._data_to_store())
        await super().async_shutdown()

    @callback
    def _on_input_change(self, event: Event[EventStateChangedData]) -> None:
        self.hass.async_create_task(self.async_refresh())

    @callback
    def _on_quarter(self, now: datetime) -> None:
        self.hass.async_create_task(self.async_refresh())

    @callback
    def _charger_changed(self) -> None:
        self.async_update_listeners()

    # -- settings used by the entities --------------------------------------

    async def async_set_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value
        self._save()
        if key == SET_GARO_SYNC and not value and self.garo is not None:
            # Sync switched off: leave an empty box schedule behind.
            await self.garo.async_sync([])
            self._garo_last_ranges = None
        await self.async_refresh()

    async def async_force_window(self, start: datetime, end: datetime) -> None:
        self.settings[SET_WINDOW_START] = start
        self.settings[SET_WINDOW_END] = end
        self._save()
        await self.async_refresh()

    # -- inputs --------------------------------------------------------------

    def _state_float(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    async def _nordpool_slots(self, entity_id: str) -> list[PriceSlot]:
        """Prices from the official Nord Pool integration (it has no attributes)."""
        entry = er.async_get(self.hass).async_get(entity_id)
        if entry is None or entry.platform != "nordpool" or not entry.config_entry_id:
            return []
        now = dt_util.now()
        result: list[PriceSlot] = []
        for day in (now.date(), now.date() + timedelta(days=1)):
            fetched = self._nordpool_fetched.get(day)
            cached = self._nordpool_cache.get(day)
            if fetched and now - fetched < NORDPOOL_REFRESH and cached is not None:
                result.extend(cached)
                continue
            slots: list[PriceSlot] = []
            try:
                response = await self.hass.services.async_call(
                    "nordpool",
                    "get_prices_for_date",
                    {"config_entry": entry.config_entry_id, "date": day.isoformat()},
                    blocking=True,
                    return_response=True,
                )
            except Exception as err:  # noqa: BLE001 - tomorrow is missing before ~13:00
                _LOGGER.debug("Nord Pool prices for %s not available: %s", day, err)
                response = None
            if isinstance(response, dict) and response:
                area = self.options.get(CONF_NORDPOOL_AREA) or next(iter(response))
                # The service returns currency/MWh; show currency/kWh.
                slots = parse_list(response.get(area), scale=0.001)
            self._nordpool_cache[day] = slots
            self._nordpool_fetched[day] = now
            result.extend(slots)
        for old in [d for d in self._nordpool_cache if d < now.date()]:
            self._nordpool_cache.pop(old, None)
            self._nordpool_fetched.pop(old, None)
        return result

    async def _collect_prices(self) -> None:
        tz = dt_util.get_default_time_zone()
        groups: list[list[PriceSlot]] = []
        self.unit = None
        for entity_id in self.options.get(CONF_PRICE_ENTITIES, []):
            state = self.hass.states.get(entity_id)
            slots: list[PriceSlot] = []
            if state is not None:
                slots = slots_from_attributes(state.attributes, tz)
                if self.unit is None:
                    self.unit = state.attributes.get("unit_of_measurement")
            if not slots:
                slots = await self._nordpool_slots(entity_id)
                if slots and self.unit is None and state is not None:
                    self.unit = state.attributes.get("unit_of_measurement")
            groups.append(slots)
        self.prices = merge_slots(*groups)

        forecast_groups = []
        for entity_id in self.options.get(CONF_FORECAST_ENTITIES, []):
            state = self.hass.states.get(entity_id)
            if state is not None:
                forecast_groups.append(slots_from_attributes(state.attributes, tz))
        self.forecast = merge_slots(*forecast_groups)

    def _update_reference(self, now: datetime) -> None:
        entity_value = self._state_float(self.options.get(CONF_REFERENCE_ENTITY))
        # Keep our own rolling daily averages; used when no reference entity is set.
        by_day: dict[str, list[PriceSlot]] = {}
        for slot in self.prices:
            by_day.setdefault(dt_util.as_local(slot.start).date().isoformat(), []).append(slot)
        changed = False
        for day, slots in by_day.items():
            if len(slots) >= 20:  # a (nearly) complete day
                value = average(slots)
                if value is not None and self.daily_averages.get(day) != round(value, 4):
                    self.daily_averages[day] = round(value, 4)
                    changed = True
        days = int(self.options.get(CONF_REFERENCE_DAYS, DEFAULT_REFERENCE_DAYS))
        keep = sorted(self.daily_averages)[-max(days, 1) * 2 :]
        if len(keep) != len(self.daily_averages):
            self.daily_averages = {k: self.daily_averages[k] for k in keep}
            changed = True
        if changed:
            self._save()

        if entity_value is not None:
            self.reference_price = entity_value
            return
        today = now.date().isoformat()
        recent = [v for k, v in sorted(self.daily_averages.items()) if k <= today][-days:]
        self.reference_price = sum(recent) / len(recent) if recent else average(self.prices)

    def _update_duration(self) -> None:
        manual = timedelta(hours=float(self.settings.get(SET_DURATION_HOURS) or 0))
        self.soc = self._state_float(self.options.get(CONF_SOC_ENTITY))
        battery = float(self.options.get(CONF_BATTERY_KWH) or 0)
        power = float(self.options.get(CONF_CHARGER_KW) or 0)
        if self.soc is not None and battery > 0 and power > 0:
            self.duration = needed_duration_from_soc(
                self.soc,
                float(self.settings.get(SET_TARGET_SOC) or 0),
                battery,
                power,
                float(self.options.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)) / 100.0,
            )
        else:
            self.duration = manual

    # -- the update ------------------------------------------------------------

    async def _async_update_data(self) -> Plan:
        now = dt_util.now()
        await self._collect_prices()
        self._update_reference(now)
        self._update_duration()

        settings = self.settings
        if settings.get(SET_DEADLINE_ENABLED):
            deadline = settings.get(SET_DEADLINE)
            if deadline is None or deadline <= now:
                # A passed deadline switches itself off, like a one-shot alarm.
                settings[SET_DEADLINE_ENABLED] = False
                self._save()
        deadline = settings.get(SET_DEADLINE) if settings.get(SET_DEADLINE_ENABLED) else None

        windows: list[tuple[datetime, datetime]] = []
        start, end = settings.get(SET_WINDOW_START), settings.get(SET_WINDOW_END)
        if start and end and end > start and end > now:
            windows.append((start, end))

        max_wait = float(self.options.get(CONF_MAX_WAIT_HOURS, DEFAULT_MAX_WAIT_HOURS))
        waited_too_long = self.last_charge_end is not None and now - self.last_charge_end > timedelta(hours=max_wait)

        max_price = float(settings.get(SET_MAX_PRICE) or 0)
        relative = float(settings.get(SET_RELATIVE_LIMIT) or 0)
        plan = make_plan(
            PlanInput(
                now=now,
                prices=self.prices,
                duration=self.duration,
                forecast=self.forecast,
                max_price=max_price if max_price > 0 else None,
                relative_limit_pct=relative if relative > 0 else None,
                reference_price=self.reference_price,
                deadline=deadline,
                deadline_respects_limits=settings.get(SET_DEADLINE_MODE) == DEADLINE_LIMITS,
                force_windows=windows,
                currently_charging=bool(self._last_charge_now),
                hysteresis_pct=float(self.options.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)),
                forecast_margin_pct=float(self.options.get(CONF_FORECAST_MARGIN, DEFAULT_FORECAST_MARGIN)),
                use_forecast=bool(settings.get(SET_USE_FORECAST)) and not waited_too_long,
            )
        )

        mode = settings.get(SET_MODE)
        if mode == MODE_PAUSED:
            plan.charge_now = False
            plan.reason = Reason.PAUSED
        elif mode == MODE_FORCE:
            plan.charge_now = True
            plan.reason = Reason.FORCED

        self._track_sessions(plan.charge_now, now)
        await self._drive_charger(plan, mode)
        await self._drive_garo(plan, windows, mode, now)
        return plan

    def _track_sessions(self, charge_now: bool, now: datetime) -> None:
        if charge_now and not self._last_charge_now:
            self._session_start = now
        elif not charge_now and self._last_charge_now and self._session_start:
            if now - self._session_start >= MIN_SESSION_FOR_LAST_CHARGE:
                self.last_charge_end = now
                self._save()
            self._session_start = None
        self._last_charge_now = charge_now

    async def _drive_charger(self, plan: Plan, mode: str) -> None:
        controlling = bool(self.settings.get(SET_CHARGER_CONTROL)) and mode != MODE_PAUSED
        if not controlling:
            if self._last_wanted:
                # We started the charger; stop it once when handing over.
                await self.charger.async_set(False)
            self._last_wanted = None
            return
        if plan.charge_now != self._last_wanted:
            self._last_wanted = plan.charge_now
            await self.charger.async_set(plan.charge_now)

    async def _drive_garo(
        self,
        plan: Plan,
        windows: list[tuple[datetime, datetime]],
        mode: str,
        now: datetime,
    ) -> None:
        if self.garo is None or not self.settings.get(SET_GARO_SYNC):
            return
        if mode == MODE_PAUSED or not self.settings.get(SET_CHARGER_CONTROL):
            ranges: list[tuple[datetime, datetime]] = []
        else:
            ranges = merge_ranges(plan.slots, windows)
        due = self._garo_next_sync is None or now >= self._garo_next_sync
        if ranges == self._garo_last_ranges and not due:
            return
        ok = await self.garo.async_sync(ranges)
        self._garo_last_ranges = ranges if ok else None
        self._garo_next_sync = now + (GARO_SYNC_INTERVAL if ok else timedelta(minutes=1))
