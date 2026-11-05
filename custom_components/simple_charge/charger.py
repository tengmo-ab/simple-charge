"""Send start/stop to the charger and make sure it sticks.

The controller is edge triggered: it only acts when the plan changes between
"charge" and "do not charge" (and once at start-up). It does not fight other
automations, a solar controller or a person who changes the charger by hand in
between. When it does act, it keeps retrying until the charger reports the
wanted state, which helps chargers with flaky Wi-Fi.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
import logging
from typing import Any

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_CONTROL_TYPE,
    CONF_LIMITER_SWITCH,
    CONF_SELECT_ENTITY,
    CONF_SELECT_OFF,
    CONF_SELECT_ON,
    CONF_START_SCRIPT,
    CONF_STOP_SCRIPT,
    CONF_SWITCH_ENTITY,
    CONTROL_NONE,
    CONTROL_SCRIPT,
    CONTROL_SELECT,
    CONTROL_SWITCH,
)

_LOGGER = logging.getLogger(__name__)

RETRY_DELAYS = (10, 20, 30, 60)  # seconds, the last one repeats
GIVE_UP_AFTER = 2 * 3600  # seconds

STATUS_IDLE = "idle"
STATUS_OK = "ok"
STATUS_PENDING = "pending"
STATUS_UNAVAILABLE = "unavailable"
STATUS_FAILED = "failed"


class ChargerController:
    """Turns the charger on or off through a switch, a select or two scripts."""

    def __init__(
        self,
        hass: HomeAssistant,
        options: Mapping[str, Any],
        on_change: Callable[[], None],
    ) -> None:
        self.hass = hass
        self.control_type: str = options.get(CONF_CONTROL_TYPE, CONTROL_NONE)
        self.switch_entity: str | None = options.get(CONF_SWITCH_ENTITY)
        self.select_entity: str | None = options.get(CONF_SELECT_ENTITY)
        self.select_on: str | None = options.get(CONF_SELECT_ON)
        self.select_off: str | None = options.get(CONF_SELECT_OFF)
        self.start_script: str | None = options.get(CONF_START_SCRIPT)
        self.stop_script: str | None = options.get(CONF_STOP_SCRIPT)
        self.limiter_switch: str | None = options.get(CONF_LIMITER_SWITCH) or None
        self._on_change = on_change
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._unsub: Callable[[], None] | None = None
        self.status: str = STATUS_IDLE
        self.wanted: bool | None = None
        self.attempts: int = 0

    @property
    def target_entity(self) -> str | None:
        if self.control_type == CONTROL_SWITCH:
            return self.switch_entity
        if self.control_type == CONTROL_SELECT:
            return self.select_entity
        return None

    @property
    def enabled(self) -> bool:
        if self.control_type == CONTROL_SWITCH:
            return bool(self.switch_entity)
        if self.control_type == CONTROL_SELECT:
            return bool(self.select_entity and self.select_on and self.select_off)
        if self.control_type == CONTROL_SCRIPT:
            return bool(self.start_script or self.stop_script)
        return False

    @callback
    def async_start(self) -> None:
        if self.target_entity:
            self._unsub = async_track_state_change_event(self.hass, [self.target_entity], self._on_target_change)

    @callback
    def _on_target_change(self, event: Event[EventStateChangedData]) -> None:
        self._wake.set()

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        await self._cancel()

    async def _cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def is_in_state(self, want: bool) -> bool | None:
        """True/False if the charger reports the wanted state, None if unknown."""
        entity = self.target_entity
        if entity is None:
            return None
        state = self.hass.states.get(entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        if self.control_type == CONTROL_SWITCH:
            return (state.state == STATE_ON) == want
        return state.state == (self.select_on if want else self.select_off)

    async def async_set(self, want: bool) -> None:
        """Start (or replace) the job that brings the charger to ``want``."""
        if not self.enabled:
            return
        await self._cancel()
        self.wanted = want
        self.attempts = 0
        self._task = self.hass.async_create_background_task(self._run(want), f"simple_charge charger {'on' if want else 'off'}")

    def _set_status(self, status: str) -> None:
        if status != self.status:
            self.status = status
            self._on_change()

    async def _run(self, want: bool) -> None:
        loop = asyncio.get_running_loop()
        give_up_at = loop.time() + GIVE_UP_AFTER

        if self.control_type == CONTROL_SCRIPT:
            await self._command(want)
            self._set_status(STATUS_OK)
            return

        while True:
            current = self.is_in_state(want)
            if current:
                self._set_status(STATUS_OK)
                return
            if loop.time() > give_up_at:
                _LOGGER.warning(
                    "Gave up turning %s %s after %s attempts",
                    self.target_entity,
                    "on" if want else "off",
                    self.attempts,
                )
                self._set_status(STATUS_FAILED)
                return

            if current is None:
                # Charger offline: wait until it shows up again.
                self._set_status(STATUS_UNAVAILABLE)
                delay = 60
            else:
                self._set_status(STATUS_PENDING)
                await self._command(want)
                delay = RETRY_DELAYS[min(self.attempts, len(RETRY_DELAYS) - 1)]
                self.attempts += 1

            self._wake.clear()
            try:
                async with asyncio.timeout(delay):
                    await self._wake.wait()
                # The state changed; give the device a moment to settle.
                await asyncio.sleep(2)
            except TimeoutError:
                pass

    async def _command(self, want: bool) -> None:
        try:
            if self.limiter_switch:
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_off" if want else "turn_on",
                    {"entity_id": self.limiter_switch},
                    blocking=True,
                )
                await asyncio.sleep(2)
            if self.control_type == CONTROL_SWITCH and self.switch_entity:
                domain = self.switch_entity.split(".", 1)[0]
                await self.hass.services.async_call(
                    domain,
                    "turn_on" if want else "turn_off",
                    {"entity_id": self.switch_entity},
                    blocking=True,
                )
            elif self.control_type == CONTROL_SELECT and self.select_entity:
                domain = self.select_entity.split(".", 1)[0]
                await self.hass.services.async_call(
                    domain,
                    "select_option",
                    {
                        "entity_id": self.select_entity,
                        "option": self.select_on if want else self.select_off,
                    },
                    blocking=True,
                )
            elif self.control_type == CONTROL_SCRIPT:
                script = self.start_script if want else self.stop_script
                if script:
                    await self.hass.services.async_call("script", "turn_on", {"entity_id": script}, blocking=False)
        except Exception as err:  # noqa: BLE001 - keep retrying whatever the device says
            _LOGGER.debug("Charger command failed (will retry): %s", err)
