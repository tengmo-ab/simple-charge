"""The charging time is per round: charged time is booked and not planned again."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from simple_charge.planner import (
    ROUND_MAX_STEP,
    ROUND_RESET_GAP,
    ChargeRound,
    PlanInput,
    PriceSlot,
    make_plan,
)

TZ = ZoneInfo("Europe/Stockholm")
Q = timedelta(minutes=15)
START = datetime(2026, 11, 5, 20, 0, tzinfo=TZ)
# Real SE3 quarter prices (öre/kWh) for the night 5-6 Nov 2026, 20:00-08:00.
NIGHT = [
    144,
    138,
    134,
    107,
    101,
    98,
    101,
    98,
    89,
    91,
    87,
    95,
    88,
    83,
    82,
    82,
    83,
    79,
    77,
    76,
    81,
    78,
    78,
    78,
    76,
    76,
    57,
    68,
    74,
    73,
    91,
    100,
    114,
    110,
    118,
    124,
    83,
    100,
    119,
    124,
    170,
    225,
    240,
    246,
    246,
    290,
    306,
    315,
]


def night_prices() -> list[PriceSlot]:
    prices = [PriceSlot(START + i * Q, START + (i + 1) * Q, p) for i, p in enumerate(NIGHT)]
    # Rest of the known day: expensive.
    for i in range(len(NIGHT), len(NIGHT) + 64):
        prices.append(PriceSlot(START + i * Q, START + (i + 1) * Q, 250))
    return prices


def simulate(duration: timedelta, use_round: bool, minutes: int = 12 * 60) -> list[datetime]:
    """Run the planner every minute like the coordinator; return the minutes that charged."""
    prices = night_prices()
    rnd = ChargeRound()
    charging = False
    charged: list[datetime] = []
    for m in range(minutes):
        now = START + timedelta(minutes=m)
        rnd.advance(now, charging)
        needed = rnd.remaining(duration) if use_round else duration
        plan = make_plan(PlanInput(now=now, prices=prices, duration=needed, max_price=85, currently_charging=charging))
        charging = plan.charge_now
        if charging:
            charged.append(now)
    return charged


def test_round_charges_exactly_the_first_plan():
    charged = simulate(timedelta(hours=2), use_round=True)
    assert len(charged) == 120
    quarters = sorted({c.replace(minute=c.minute // 15 * 15) for c in charged})
    assert [q.strftime("%H:%M") for q in quarters] == ["00:30", "00:45", "02:00", "02:15", "02:30", "02:45", "03:00", "03:15"]


def test_without_round_the_plan_slides():
    # The behaviour before 2.3.0, kept as a regression marker: far more than 2 h.
    assert len(simulate(timedelta(hours=2), use_round=False)) > 150


def test_round_resets_after_a_long_pause():
    rnd = ChargeRound()
    t = START
    rnd.advance(t, False)
    for _ in range(30):
        t += timedelta(minutes=1)
        rnd.advance(t, True)
    assert rnd.charged == timedelta(minutes=30)
    assert rnd.remaining(timedelta(hours=2)) == timedelta(minutes=90)
    rnd.advance(t + ROUND_RESET_GAP - timedelta(minutes=1), False)
    assert rnd.charged == timedelta(minutes=30)
    rnd.advance(t + ROUND_RESET_GAP, False)
    assert rnd.charged == timedelta()
    assert rnd.remaining(timedelta(hours=2)) == timedelta(hours=2)


def test_one_step_is_capped_after_a_restart():
    rnd = ChargeRound(last_tick=START)
    rnd.advance(START + timedelta(hours=3), True)
    assert rnd.charged == ROUND_MAX_STEP


def test_done_round_needs_nothing_more():
    rnd = ChargeRound(charged=timedelta(hours=2) - timedelta(seconds=20))
    assert rnd.remaining(timedelta(hours=2)) == timedelta()
