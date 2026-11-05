"""Read price slots out of Home Assistant entity attributes.

Different price integrations expose their data differently. This module
understands the common shapes without importing Home Assistant:

* Nord Pool (HACS, custom-components/nordpool): ``raw_today`` / ``raw_tomorrow``
  as ``[{"start", "end", "value"}]``.
* Energi Data Service: ``raw_today`` / ``raw_tomorrow`` / ``forecast`` as
  ``[{"hour", "price"}]``.
* ENTSO-e: ``prices_today`` / ``prices_tomorrow`` / ``prices`` as
  ``[{"time", "price"}]``.
* Template / custom sensors and forecast sensors: ``data`` / ``prices`` /
  ``forecast`` as ``[{"start", "end", "price"}]``.

Lists of bare numbers (no timestamps) are ignored. Slots without an explicit
end get the distance to the next slot, or the most common slot length.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, tzinfo
from typing import Any

from .planner import PriceSlot

LIST_ATTRIBUTES = (
    "raw_today",
    "raw_tomorrow",
    "data",
    "prices_today",
    "prices_tomorrow",
    "prices",
    "today_prices",
    "tomorrow_prices",
    "forecast",
    "price_forecast",
)
START_KEYS = ("start", "startsAt", "starts_at", "start_time", "time", "hour", "from", "datetime")
END_KEYS = ("end", "endsAt", "ends_at", "end_time", "till", "to")
PRICE_KEYS = ("price", "value", "total", "price_per_kwh", "cost")


def _to_datetime(value: Any, default_tz: tzinfo | None) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        if default_tz is None:
            return None
        result = result.replace(tzinfo=default_tz)
    return result


def _first(item: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def parse_list(items: Any, default_tz: tzinfo | None = None, scale: float = 1.0) -> list[PriceSlot]:
    """Turn one attribute list into price slots (unsorted input is fine)."""
    if not isinstance(items, (list, tuple)):
        return []
    raw: list[tuple[datetime, datetime | None, float]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        start = _to_datetime(_first(item, START_KEYS), default_tz)
        price = _first(item, PRICE_KEYS)
        if start is None or price is None:
            continue
        try:
            price_value = float(price) * scale
        except (TypeError, ValueError):
            continue
        end = _to_datetime(_first(item, END_KEYS), default_tz)
        raw.append((start, end, price_value))
    if not raw:
        return []

    raw.sort(key=lambda r: r[0])
    gaps = [b[0] - a[0] for a, b in zip(raw, raw[1:], strict=False) if b[0] > a[0]]
    typical = Counter(gaps).most_common(1)[0][0] if gaps else timedelta(hours=1)

    slots: list[PriceSlot] = []
    for index, (start, end, price) in enumerate(raw):
        if end is None or end <= start:
            nxt = raw[index + 1][0] if index + 1 < len(raw) else None
            end = nxt if nxt is not None and nxt - start <= typical * 2 and nxt > start else start + typical
        slots.append(PriceSlot(start, end, price))
    return slots


def slots_from_attributes(attributes: Mapping[str, Any], default_tz: tzinfo | None = None) -> list[PriceSlot]:
    """All price slots found in one entity's attributes."""
    found: list[PriceSlot] = []
    for key in LIST_ATTRIBUTES:
        if key in attributes:
            found.extend(parse_list(attributes[key], default_tz))
    return found


def merge_slots(*groups: Iterable[PriceSlot]) -> list[PriceSlot]:
    """Combine sources; the first source that has a slot for a start time wins."""
    by_start: dict[datetime, PriceSlot] = {}
    for group in groups:
        for slot in group:
            by_start.setdefault(slot.start, slot)
    return sorted(by_start.values(), key=lambda s: s.start)


def average(slots: Iterable[PriceSlot]) -> float | None:
    """Time weighted average price."""
    total = 0.0
    weight = 0.0
    for slot in slots:
        seconds = slot.length.total_seconds()
        total += slot.price * seconds
        weight += seconds
    return total / weight if weight else None
