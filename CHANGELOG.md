# Changelog

## 2.3.0 – 2026-11-07

- **Fix:** a fixed charging time is now per round. Time already charged is booked and
  not planned again, so "2 h" means 2 h. Before, the plan was re-made every quarter
  with the full 2 h still to go, so it slid forward and kept the charger on much
  longer than asked (seen live: on 00:30–03:30 instead of the eight planned quarters).
- A round ends after 6 h without charging; the next one starts with the full time.
  With a battery level sensor nothing changes (the car's level already says what is left).
- `sensor.*_needed_charging_time` now shows the time still needed in this round, with
  attributes `total_hours`, `charged_this_round_hours`, `round_last_charging` and
  `from_battery_level`.

## 2.2.0 – 2026-11-05

- `sensor.*_plan` has a new attribute `forecast_slots`: the forecast slots the
  planner is waiting for (with their forecast price), so dashboards can draw them.

## 2.1.1 – 2026-11-05

- Entity ids are always English (`binary_sensor.simple_charge_charge_now`, …),
  also when Home Assistant runs in another language. Names stay translated.
  Existing entities keep their ids; remove and re-add the entry to get the new ones.

## 2.1.0 – 2026-11-05

- New select **Ready by mode**: *Must finish (ignore price)* (as before) or
  *Within price limits*, which only uses slots before the deadline that are also
  below the max price / relative limit. The car may then end up only partly
  charged, but never at an expensive price.
- Tested on Home Assistant 2026.11 and its built-in Marketplace.

## 2.0.0 – 2026-11-05

First release as a Home Assistant integration (version 1 was a template
binary sensor and two automations).

- UI setup and options, English and Swedish.
- Planner: cheapest slots covering the wanted charging time, fixed and relative
  price limits, hysteresis for a running slot, "ready by" deadline, force window.
- Optional price forecast: waits for a clearly cheaper day (with a safety margin
  and a maximum wait).
- Optional battery level based charging time (battery size, charger power, target level).
- Works with any price sensor that has a timestamped price list, and with the
  official Nord Pool integration.
- Charger control through a switch, a mode select or scripts, edge triggered with
  retries until the charger confirms (for flaky Wi-Fi); optional limiter switch.
- Modes Smart / Charge now / Paused, and a "Control charger" switch for plan-only
  use together with a solar controller.
- Optional Garo wallbox schedule mirroring through the garo_wallbox integration.
- Actions `simple_charge.force_charge` and `simple_charge.clear_force`.
