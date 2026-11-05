from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from simple_charge.planner import (
    PlanInput,
    PriceSlot,
    Reason,
    compute_threshold,
    make_plan,
    merge_ranges,
    needed_duration_from_soc,
)

TZ = ZoneInfo("Europe/Stockholm")
DAY = datetime(2026, 11, 5, 0, 0, tzinfo=TZ)
Q = timedelta(minutes=15)


def quarters(start: datetime, prices: list[float], forecast: bool = False) -> list[PriceSlot]:
    return [PriceSlot(start + i * Q, start + (i + 1) * Q, p, forecast) for i, p in enumerate(prices)]


def day_prices(cheap_at: dict[int, float] | None = None, base: float = 100.0) -> list[float]:
    prices = [base] * 96
    for index, price in (cheap_at or {}).items():
        prices[index] = price
    return prices


def test_picks_cheapest_quarters_and_charges_inside_them():
    prices = quarters(DAY, day_prices({8: 10, 9: 11, 40: 12, 41: 13, 60: 50}))
    plan = make_plan(PlanInput(now=DAY + 8 * Q + timedelta(minutes=3), prices=prices, duration=timedelta(hours=1)))
    assert [s.price for s in plan.slots] == [10, 11, 12, 13]
    assert plan.charge_now is True
    assert plan.reason is Reason.CHARGING


def test_scheduled_but_not_now():
    prices = quarters(DAY, day_prices({40: 1, 41: 1}))
    plan = make_plan(PlanInput(now=DAY, prices=prices, duration=timedelta(minutes=30)))
    assert plan.charge_now is False
    assert plan.reason is Reason.SCHEDULED
    assert plan.next_start(DAY) == DAY + 40 * Q


def test_thresholds_static_and_relative_take_the_lower():
    assert compute_threshold(85, 50, 256) == 85
    assert compute_threshold(200, 50, 256) == 128
    assert compute_threshold(None, None, 256) is None
    assert compute_threshold(None, 50, None) is None


def test_too_expensive_when_nothing_below_limit():
    prices = quarters(DAY, day_prices(base=150))
    plan = make_plan(PlanInput(now=DAY, prices=prices, duration=timedelta(hours=2), max_price=85))
    assert plan.slots == []
    assert plan.reason is Reason.TOO_EXPENSIVE


def test_hysteresis_keeps_running_slot():
    prices = quarters(DAY, day_prices({0: 90}, base=200))
    data = PlanInput(now=DAY + timedelta(minutes=5), prices=prices, duration=timedelta(hours=1), max_price=85)
    assert make_plan(data).charge_now is False
    data.currently_charging = True  # 90 <= 85 * 1.15
    assert make_plan(data).charge_now is True


def test_past_slots_are_ignored():
    prices = quarters(DAY, day_prices({0: 1, 1: 1, 50: 5}))
    plan = make_plan(PlanInput(now=DAY + 2 * Q, prices=prices, duration=timedelta(minutes=15)))
    assert [s.start for s in plan.slots] == [DAY + 50 * Q]


def test_deadline_ignores_price_caps_and_forecast():
    prices = quarters(DAY, day_prices({80: 1}, base=300))
    forecast = quarters(DAY + timedelta(days=1), [1] * 96, forecast=True)
    plan = make_plan(
        PlanInput(
            now=DAY,
            prices=prices,
            duration=timedelta(minutes=30),
            max_price=85,
            forecast=forecast,
            deadline=DAY + 20 * Q,
        )
    )
    assert len(plan.slots) == 2
    assert all(s.start < DAY + 20 * Q for s in plan.slots)
    assert plan.waiting_for == []


def test_forecast_makes_it_wait_for_a_clearly_cheaper_day():
    prices = quarters(DAY, day_prices(base=80))
    forecast = quarters(DAY + timedelta(days=1), [40] * 96, forecast=True)
    plan = make_plan(PlanInput(now=DAY, prices=prices, duration=timedelta(hours=2), forecast=forecast))
    assert plan.slots == []
    assert plan.reason is Reason.WAITING_FOR_FORECAST
    assert len(plan.waiting_for) == 8


def test_forecast_margin_prefers_known_prices_when_close():
    prices = quarters(DAY, day_prices(base=80))
    forecast = quarters(DAY + timedelta(days=1), [72] * 96, forecast=True)  # 72 * 1.15 > 80
    plan = make_plan(PlanInput(now=DAY, prices=prices, duration=timedelta(hours=2), forecast=forecast))
    assert len(plan.slots) == 8
    assert plan.waiting_for == []


def test_forecast_disabled_or_beyond_horizon():
    prices = quarters(DAY, day_prices(base=80))
    far = quarters(DAY + timedelta(days=3), [1] * 96, forecast=True)
    plan = make_plan(PlanInput(now=DAY, prices=prices, duration=timedelta(hours=1), forecast=far))
    assert len(plan.slots) == 4
    near = quarters(DAY + timedelta(days=1), [1] * 96, forecast=True)
    plan = make_plan(PlanInput(now=DAY, prices=prices, duration=timedelta(hours=1), forecast=near, use_forecast=False))
    assert len(plan.slots) == 4


def test_forecast_overlapping_known_prices_is_ignored():
    prices = quarters(DAY, day_prices(base=80))
    overlap = quarters(DAY, [1] * 96, forecast=True)
    plan = make_plan(PlanInput(now=DAY, prices=prices, duration=timedelta(hours=1), forecast=overlap))
    assert len(plan.slots) == 4


def test_force_window_charges_even_when_expensive():
    prices = quarters(DAY, day_prices(base=500))
    plan = make_plan(
        PlanInput(
            now=DAY + timedelta(hours=1),
            prices=prices,
            duration=timedelta(hours=1),
            max_price=10,
            force_windows=[(DAY, DAY + timedelta(hours=2))],
        )
    )
    assert plan.charge_now is True
    assert plan.reason is Reason.FORCE_WINDOW


def test_no_prices_and_nothing_needed():
    assert make_plan(PlanInput(now=DAY, prices=[], duration=timedelta(hours=1))).reason is Reason.NO_PRICES
    prices = quarters(DAY, day_prices())
    assert make_plan(PlanInput(now=DAY, prices=prices, duration=timedelta())).reason is Reason.NOTHING_NEEDED


def test_hourly_prices_work_too():
    hourly = [PriceSlot(DAY + timedelta(hours=h), DAY + timedelta(hours=h + 1), 100 - h) for h in range(24)]
    plan = make_plan(PlanInput(now=DAY, prices=hourly, duration=timedelta(hours=2)))
    assert [s.price for s in plan.slots] == [78, 77]


def test_merge_ranges_and_average():
    slots = quarters(DAY, [10, 20, 30])
    plan = make_plan(PlanInput(now=DAY, prices=slots, duration=timedelta(minutes=45)))
    assert merge_ranges(plan.slots) == [(DAY, DAY + 3 * Q)]
    assert plan.average_price == 20
    assert merge_ranges([], [(DAY, DAY + Q), (DAY + Q, DAY + 2 * Q)]) == [(DAY, DAY + 2 * Q)]


def test_soc_duration():
    # 64 kWh, 20 -> 80 %, 11 kW at 90 % = 38.4 / 9.9 h
    duration = needed_duration_from_soc(20, 80, 64, 11, 0.9)
    assert abs(duration.total_seconds() / 3600 - 38.4 / 9.9) < 1e-9
    assert needed_duration_from_soc(90, 80, 64, 11) == timedelta()
    assert needed_duration_from_soc(20, 80, 64, 0) == timedelta()
