from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from simple_charge.planner import PriceSlot
from simple_charge.prices import average, merge_slots, parse_list, slots_from_attributes

TZ = ZoneInfo("Europe/Stockholm")


def test_template_style_data_attribute():
    attrs = {
        "data": [
            {"start": "2026-11-04T23:00:00+00:00", "end": "2026-11-04T23:15:00+00:00", "price": 78.9},
            {"start": "2026-11-04T23:15:00+00:00", "end": "2026-11-04T23:30:00+00:00", "price": 82.3},
        ],
        "prices": [78.9, 82.3],  # bare numbers are ignored
    }
    slots = slots_from_attributes(attrs, TZ)
    assert len(slots) == 2
    assert slots[0].price == 78.9
    assert slots[0].length == timedelta(minutes=15)


def test_nordpool_hacs_raw_today_tomorrow_with_datetimes():
    start = datetime(2026, 11, 5, 0, 0, tzinfo=TZ)
    raw = [{"start": start + timedelta(hours=h), "end": start + timedelta(hours=h + 1), "value": 1.0 + h} for h in range(3)]
    slots = slots_from_attributes({"raw_today": raw, "raw_tomorrow": [], "today": [1, 2, 3]}, TZ)
    assert [s.price for s in slots] == [1.0, 2.0, 3.0]


def test_energi_data_service_hour_without_end_infers_length():
    items = [{"hour": "2026-11-05T00:00:00+01:00", "price": 1.1}, {"hour": "2026-11-05T01:00:00+01:00", "price": 1.2}]
    slots = parse_list(items)
    assert [s.length for s in slots] == [timedelta(hours=1), timedelta(hours=1)]


def test_quarters_without_end_infer_15_minutes():
    items = [{"time": f"2026-11-05T00:{m:02d}:00+01:00", "price": 1} for m in (0, 15, 30, 45)]
    assert {s.length for s in parse_list(items)} == {timedelta(minutes=15)}


def test_naive_timestamps_use_default_tz_and_garbage_is_skipped():
    items = [{"start": "2026-11-05T00:00:00", "price": "1.5"}, {"start": "nope", "price": 1}, {"price": 3}, "x"]
    slots = parse_list(items, TZ)
    assert len(slots) == 1 and slots[0].start.tzinfo is TZ and slots[0].price == 1.5


def test_scale_for_mwh():
    slots = parse_list([{"start": "2026-11-05T00:00:00+01:00", "end": "2026-11-05T00:15:00+01:00", "price": 1000}], scale=0.001)
    assert slots[0].price == 1.0


def test_merge_first_source_wins_and_average():
    a = datetime(2026, 11, 5, tzinfo=TZ)
    first = [PriceSlot(a, a + timedelta(minutes=15), 1)]
    second = [PriceSlot(a, a + timedelta(minutes=15), 9), PriceSlot(a + timedelta(minutes=15), a + timedelta(minutes=30), 3)]
    merged = merge_slots(first, second)
    assert [s.price for s in merged] == [1, 3]
    assert average(merged) == 2
    assert average([]) is None
