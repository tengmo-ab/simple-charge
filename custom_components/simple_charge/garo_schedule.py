"""Optional: mirror the charging plan into a Garo wallbox's own weekly schedule.

The Garo box can charge on its own built-in schedule when it is in SCHEMA mode.
Writing the plan there means the car still charges at the planned times if the
box loses Wi-Fi. This uses the services of the ``garo_wallbox`` integration
(github.com/sockless-coding/garo_wallbox); nothing here talks to the box
directly.

The Garo schedule repeats every week, so entries are removed again as soon as
their time has passed. Simple Charge owns the whole schedule while the sync is
on: entries it did not plan are removed.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

GARO_DOMAIN = "garo_wallbox"
WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
MAX_AHEAD = timedelta(days=6)  # never write further ahead than the weekly repeat

Entry = tuple[str, str, str]  # (weekday, "HH:MM", "HH:MM")


def _hhmm(value: Any) -> str | None:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, str) and len(value) >= 5:
        return value[:5]
    return None


def ranges_to_entries(ranges: list[tuple[datetime, datetime]], now: datetime) -> set[Entry]:
    """Split local ranges at midnight and turn them into weekday entries."""
    entries: set[Entry] = set()
    limit = now + MAX_AHEAD
    for start, end in ranges:
        start = dt_util.as_local(start)
        end = dt_util.as_local(min(end, limit))
        if end <= now or start >= end:
            continue
        cursor = start
        while cursor < end:
            midnight = datetime.combine(cursor.date() + timedelta(days=1), time(0), tzinfo=cursor.tzinfo)
            piece_end = min(end, midnight)
            stop = "23:59" if piece_end == midnight else piece_end.strftime("%H:%M")
            begin = cursor.strftime("%H:%M")
            if begin != stop:
                entries.add((WEEKDAYS[cursor.weekday()], begin, stop))
            cursor = piece_end
    return entries


class GaroScheduleSync:
    """Keeps the Garo schedule equal to the plan."""

    def __init__(self, hass: HomeAssistant, entity_id: str, charge_limit: int) -> None:
        self.hass = hass
        self.entity_id = entity_id
        self.charge_limit = charge_limit
        self.last_error: str | None = None
        self.last_synced: datetime | None = None

    def current_entries(self) -> list[dict[str, Any]] | None:
        state = self.hass.states.get(self.entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return None
        entries = state.attributes.get("entries")
        return list(entries) if isinstance(entries, list) else []

    async def async_sync(self, ranges: list[tuple[datetime, datetime]]) -> bool:
        """Make the box schedule match ``ranges``. Returns True when in sync."""
        current = self.current_entries()
        if current is None:
            self.last_error = "schedule entity unavailable"
            return False

        now = dt_util.now()
        wanted = ranges_to_entries(ranges, now)
        today = WEEKDAYS[now.weekday()]
        clock = now.strftime("%H:%M")
        have: dict[Entry, int] = {}
        to_remove: list[int] = []
        for item in current:
            try:
                key = (
                    str(item["day_of_the_week"]).upper(),
                    _hhmm(item["start"]) or "",
                    _hhmm(item["stop"]) or "",
                )
                entry_id = int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if key not in wanted and key[0] == today and key[1] <= clock < key[2]:
                # A running entry whose already-passed start was trimmed from
                # the plan: keep it instead of interrupting the charge.
                running = next(
                    (w for w in wanted if w[0] == today and w[2] == key[2] and key[1] <= w[1] <= clock),
                    None,
                )
                if running is not None and running not in have:
                    have[running] = entry_id
                    continue
            if key in wanted and key not in have:
                have[key] = entry_id
            else:
                to_remove.append(entry_id)

        to_add = sorted(wanted - set(have))
        if not to_remove and not to_add:
            self.last_error = None
            self.last_synced = dt_util.utcnow()
            return True

        try:
            for entry_id in to_remove:
                await self.hass.services.async_call(
                    GARO_DOMAIN,
                    "remove_schedule",
                    {"entity_id": self.entity_id, "id": entry_id},
                    blocking=True,
                )
            for day, start, stop in to_add:
                await self.hass.services.async_call(
                    GARO_DOMAIN,
                    "add_schedule",
                    {
                        "entity_id": self.entity_id,
                        "day_of_the_week": day,
                        "start": start,
                        "stop": stop,
                        "charge_limit": self.charge_limit,
                    },
                    blocking=True,
                )
        except Exception as err:  # noqa: BLE001 - box offline is expected now and then
            self.last_error = str(err) or type(err).__name__
            _LOGGER.debug("Garo schedule sync failed: %s", err)
            return False

        _LOGGER.debug("Garo schedule: removed %s, added %s", to_remove, to_add)
        self.last_error = None
        self.last_synced = dt_util.utcnow()
        return True
