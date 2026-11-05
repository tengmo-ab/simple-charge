"""Pure planning logic for Simple Charge.

No Home Assistant imports here, so the algorithm can be unit tested on its own.

The idea in one paragraph: the car needs ``duration`` of charging. Among the
price slots we know (today + tomorrow from the price source) we keep the ones
that are cheap enough (below a fixed cap and below a share of a reference
average), and pick the cheapest of them until the duration is covered. If a
price forecast for the following days is available, forecast slots join the
competition with a safety margin added to their price: when the forecast says a
later day is clearly cheaper, the known slots lose and we wait. Only known
slots are ever charged. A deadline ("ready by") overrides the price caps and
the forecast: then the cheapest slots before the deadline are used, whatever
they cost. A force window always charges.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum


class Reason(StrEnum):
    """Why the plan says charge / do not charge right now."""

    PAUSED = "paused"
    FORCED = "forced"
    FORCE_WINDOW = "force_window"
    CHARGING = "charging"
    SCHEDULED = "scheduled"
    WAITING_FOR_FORECAST = "waiting_for_forecast"
    TOO_EXPENSIVE = "too_expensive"
    NO_PRICES = "no_prices"
    NOTHING_NEEDED = "nothing_needed"


@dataclass(frozen=True, slots=True)
class PriceSlot:
    """One price interval (usually 15 minutes)."""

    start: datetime
    end: datetime
    price: float
    forecast: bool = False

    @property
    def length(self) -> timedelta:
        return self.end - self.start

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


@dataclass(slots=True)
class PlanInput:
    """Everything the planner needs. All datetimes must be timezone aware."""

    now: datetime
    prices: list[PriceSlot]
    duration: timedelta
    forecast: list[PriceSlot] = field(default_factory=list)
    max_price: float | None = None
    relative_limit_pct: float | None = None
    reference_price: float | None = None
    deadline: datetime | None = None
    force_windows: list[tuple[datetime, datetime]] = field(default_factory=list)
    currently_charging: bool = False
    hysteresis_pct: float = 15.0
    forecast_margin_pct: float = 15.0
    use_forecast: bool = True
    forecast_horizon: timedelta = timedelta(days=2)


@dataclass(slots=True)
class Plan:
    """Result of one planning round."""

    charge_now: bool
    reason: Reason
    slots: list[PriceSlot] = field(default_factory=list)
    waiting_for: list[PriceSlot] = field(default_factory=list)
    threshold: float | None = None
    active_force_window: tuple[datetime, datetime] | None = None

    @property
    def planned_duration(self) -> timedelta:
        return sum((s.length for s in self.slots), timedelta())

    @property
    def average_price(self) -> float | None:
        total = self.planned_duration.total_seconds()
        if not total:
            return None
        return sum(s.price * s.length.total_seconds() for s in self.slots) / total

    def next_start(self, now: datetime) -> datetime | None:
        """Start of the running or next planned block of slots."""
        block_start: datetime | None = None
        previous_end: datetime | None = None
        for slot in self.slots:
            if previous_end is None or slot.start > previous_end:
                block_start = slot.start
            previous_end = slot.end
            if slot.end > now:
                return block_start
        return None


def compute_threshold(
    max_price: float | None,
    relative_limit_pct: float | None,
    reference_price: float | None,
) -> float | None:
    """The price a slot must stay at or below, or None for "no limit"."""
    limits: list[float] = []
    if max_price is not None:
        limits.append(max_price)
    if relative_limit_pct and reference_price is not None:
        limits.append(reference_price * relative_limit_pct / 100.0)
    return min(limits) if limits else None


def _pick_cheapest(candidates: list[PriceSlot], needed: timedelta) -> list[PriceSlot]:
    """Cheapest slots first (earlier wins a tie) until ``needed`` is covered."""
    chosen: list[PriceSlot] = []
    covered = timedelta()
    for slot in sorted(candidates, key=lambda s: (s.price, s.start)):
        if covered >= needed:
            break
        chosen.append(slot)
        covered += slot.length
    return chosen


def make_plan(data: PlanInput) -> Plan:
    """Decide which slots to charge in and whether to charge right now."""
    now = data.now
    active_window = next(((start, end) for start, end in data.force_windows if start <= now < end), None)

    future = sorted((s for s in data.prices if s.end > now), key=lambda s: s.start)
    threshold = compute_threshold(data.max_price, data.relative_limit_pct, data.reference_price)

    plan = Plan(charge_now=False, reason=Reason.NOTHING_NEEDED, threshold=threshold)

    if data.duration > timedelta() and future:
        if data.deadline is not None:
            # "Ready by": price caps and forecast do not apply, the car must be done.
            candidates = [s for s in future if s.start < data.deadline]
            chosen = _pick_cheapest(candidates, data.duration)
            plan.slots = sorted(chosen, key=lambda s: s.start)
        else:

            def cheap_enough(slot: PriceSlot) -> bool:
                if threshold is None:
                    return True
                limit = threshold
                if data.currently_charging and slot.contains(now):
                    # Do not stop half way through a slot because the
                    # reference average moved a little.
                    limit = threshold * (1 + data.hysteresis_pct / 100.0)
                return slot.price <= limit

            candidates = [s for s in future if cheap_enough(s)]

            pool = list(candidates)
            if data.use_forecast and data.forecast:
                last_known = future[-1].end
                horizon_end = now + data.forecast_horizon
                factor = 1 + data.forecast_margin_pct / 100.0
                for f in data.forecast:
                    if f.start < last_known or f.start >= horizon_end:
                        continue
                    pessimistic = PriceSlot(f.start, f.end, f.price * factor, True)
                    if threshold is None or pessimistic.price <= threshold:
                        pool.append(pessimistic)

            chosen = _pick_cheapest(pool, data.duration)
            plan.slots = sorted((s for s in chosen if not s.forecast), key=lambda s: s.start)
            # Report forecast slots with their real forecast price, not the padded one.
            original = {f.start: f for f in data.forecast}
            plan.waiting_for = sorted((original.get(s.start, s) for s in chosen if s.forecast), key=lambda s: s.start)

    charging_slot = any(s.contains(now) for s in plan.slots)

    if active_window is not None:
        plan.charge_now = True
        plan.reason = Reason.FORCE_WINDOW
        plan.active_force_window = active_window
    elif charging_slot:
        plan.charge_now = True
        plan.reason = Reason.CHARGING
    elif data.duration <= timedelta():
        plan.reason = Reason.NOTHING_NEEDED
    elif not future:
        plan.reason = Reason.NO_PRICES
    elif plan.slots:
        plan.reason = Reason.SCHEDULED
    elif plan.waiting_for:
        plan.reason = Reason.WAITING_FOR_FORECAST
    else:
        plan.reason = Reason.TOO_EXPENSIVE
    return plan


def merge_ranges(slots: list[PriceSlot], extra: list[tuple[datetime, datetime]] | None = None) -> list[tuple[datetime, datetime]]:
    """Join touching or overlapping intervals into ranges, sorted by start."""
    intervals = sorted([(s.start, s.end) for s in slots] + list(extra or []))
    merged: list[tuple[datetime, datetime]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def needed_duration_from_soc(
    soc: float,
    target: float,
    battery_kwh: float,
    charger_kw: float,
    efficiency: float = 0.9,
) -> timedelta:
    """Charging time to go from ``soc`` to ``target`` percent."""
    if charger_kw <= 0 or battery_kwh <= 0 or efficiency <= 0:
        return timedelta()
    missing = max(0.0, min(target, 100.0) - max(soc, 0.0))
    hours = missing / 100.0 * battery_kwh / (charger_kw * efficiency)
    return timedelta(hours=hours)
