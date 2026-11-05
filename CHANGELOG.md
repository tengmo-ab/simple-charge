# Changelog

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
