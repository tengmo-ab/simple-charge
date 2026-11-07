<p align="center">
  <img src="docs/logo.png" alt="Simple Charge" height="80">
</p>

<p align="center">
  <a href="https://github.com/tengmo-ab/simple-charge/releases"><img alt="Release" src="https://img.shields.io/github/v/release/tengmo-ab/simple-charge?sort=semver"></a>
  <img alt="Marketplace / HACS custom" src="https://img.shields.io/badge/Marketplace%20%2F%20HACS-custom-41BDF5.svg">
  <img alt="Home Assistant" src="https://img.shields.io/badge/Home%20Assistant-2025.6%2B-blue">
</p>

**Simple Charge** charges your electric car in the cheapest 15-minute (or hourly)
slots of the day. It reads the spot prices you already have in Home Assistant,
picks the cheapest slots that cover the charging time you ask for, and turns
your charger on and off. It works with any charger that Home Assistant can
switch, and it can step aside completely when a solar controller should take over.

It is meant to stay simple to understand: one number for "how long", two
optional price limits, and a sensor that tells you in plain words when it will
charge and why.

## How it decides

1. **Charging time.** You set how many hours the car should get (for example 2 h).
   If you add a battery level sensor, battery size and charger power, the time is
   calculated from the car's level and your target instead.
   A fixed time is per round: time already charged counts, so 2 h means 2 h in
   total. A round ends after 6 h without charging, and the next one starts again
   with the full time.
2. **Cheap enough?** A slot may be used if it is at or below both limits you
   turned on:
   - **Max price** – a fixed cap (0 = off).
   - **Relative limit** – a percentage of a reference average (0 = off). The
     reference is a sensor you pick, or Simple Charge's own rolling average of the
     last days' prices.
3. **Cheapest first.** Among the known future slots (today + tomorrow once the
   day-ahead prices are out) it picks the cheapest until the charging time is covered.
4. **Worth waiting?** *(optional)* If you have a price forecast for the coming
   days, forecast slots compete too, made 15 % more expensive as a safety margin.
   If a later day is clearly cheaper, Simple Charge waits. It never charges on a
   forecast, and it stops waiting when the car has gone too long without a charge
   (default 72 h).
5. **Ready by.** With a deadline switched on, only slots before the deadline are
   used and the forecast is ignored. *Ready by mode* decides about price:
   - **Must finish** (default) – price limits are ignored, the car is done in time
     whatever it costs.
   - **Within price limits** – the limits still apply. The car gets the cheap slots
     before the deadline and may end up only partly charged. A short window before
     the deadline also tends to keep the charging in fewer, longer blocks.
   The deadline switches itself off once it has passed.
6. **Force window / Charge now.** A force window (or the `force_charge` action)
   charges regardless of price.

Charging "a little and often" (for example 2 h every cheap night) usually gets a
better average price for a daily-driven car than trying to hit the single cheapest
night of the week. That is the default behaviour; the forecast step adds a nudge to
skip a night when the next one looks clearly cheaper.

A slot that is already charging may cost a bit more (hysteresis, default 15 %)
before it is dropped, so a small change in the reference average does not stop
a charge halfway.

## Installation

**Home Assistant 2026.11 and later (built-in Marketplace)**

1. Settings → **Marketplace** → add a custom repository:
   `https://github.com/tengmo-ab/simple-charge`, category **Integration**
   (adding custom repositories needs the Marketplace's GitHub connection, and the
   repository must be public).
2. Install **Simple Charge** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Simple Charge.**

**Older versions with HACS:** HACS → ⋮ → **Custom repositories**, same URL, type
**Integration**, then install and restart.

Both show the release version (for example `2.1.0`), taken from the GitHub releases.

Manual install: copy `custom_components/simple_charge` into your
`config/custom_components/` folder and restart.

## Setup

| Step | What you choose |
| --- | --- |
| Prices | One or more price sensors with today's/tomorrow's prices. Optional forecast sensors and an optional reference average sensor. |
| Charger | How to start/stop charging: a **switch**, a **mode select** (one option charges, one stops), your own **start/stop scripts**, or **only plan** (use the *Charge now* sensor in your own automations). |
| Charger entities | The switch/select/scripts, plus an optional *current limiter switch* that is turned off while charging. |
| Fine tuning | Hysteresis, forecast margin, max wait, battery level + battery size + charger power, optional Garo schedule. |

Everything can be changed later under **Configure**.

### Supported price sources

Any sensor that carries a list of prices with timestamps in its attributes, for example:

| Integration | Attributes used |
| --- | --- |
| Nord Pool (HACS, `custom-components/nordpool`) | `raw_today`, `raw_tomorrow` |
| Nord Pool (official integration) | fetched with the `nordpool.get_prices_for_date` action (shown per kWh) |
| ENTSO-e | `prices_today`, `prices_tomorrow`, `prices` |
| Energi Data Service | `raw_today`, `raw_tomorrow`, `forecast` |
| Template / own sensors, AI price forecasts | `data`, `prices`, `forecast` with `start`, `end` (optional), `price`/`value` |

Several sensors are merged (for example one for today and one for tomorrow).
Prices are used in the sensor's own unit, so set the max price in that unit too.

## Entities

| Entity | Purpose |
| --- | --- |
| `binary_sensor.<name>_charge_now` | **On when the car should charge.** Use it in other automations if you like. Attributes: `reason`, `next_start`. |
| `sensor.<name>_plan` | Planned charging in plain text, e.g. `5/11 23:15–00:00, 6/11 02:00–03:00`. Attributes: `slots`, `forecast_slots` (what it waits for), average price, price limit. |
| `sensor.<name>_status` | Why: charging, scheduled, waiting for a cheaper forecast, too expensive, paused, … |
| `sensor.<name>_next_start` | When the next (or current) charging block starts. |
| `sensor.<name>_price_limit` / `_reference_price` | The limit in use and the reference average. |
| `sensor.<name>_needed_charging_time` | Hours needed (fixed, or from battery level). |
| `sensor.<name>_charger_command` | Diagnostic: last command and whether the charger confirmed it. |
| `select.<name>_mode` | **Smart** (cheapest prices), **Charge now** (always on), **Paused** (hands off). |
| `switch.<name>_control_charger` | Off = plan only, never touch the charger. |
| `number.<name>_charging_time` | Hours to charge per plan. |
| `number.<name>_max_price` / `_relative_limit` | Price limits (0 = off). |
| `switch.<name>_ready_by` + `datetime.<name>_ready_by_time` | Finish before a time. |
| `select.<name>_ready_by_mode` | *Must finish* or *Within price limits*. |
| `datetime.<name>_force_window_start` / `_end` | Always charge inside this window. |
| `switch.<name>_use_price_forecast` | Only when forecast sensors are set up. |
| `number.<name>_target_battery_level` | Only when battery level and size are set up. |
| `switch.<name>_write_garo_schedule` | Only when a Garo schedule sensor is set up. |

### Actions

- `simple_charge.force_charge` – charge from now for `duration` (default 1 h).
- `simple_charge.clear_force` – remove the force window.

## Working together with solar charging

Simple Charge never fights other automations. It only sends a command when its own
plan flips between "charge" and "don't charge" (and once at start-up), then retries
until the charger confirms that state. In between, a solar controller or a person
may change the charger freely.

- **Paused** – Simple Charge stops the charger once if it was the one that started
  it, then keeps its hands off. Use this when solar should take over.
- **Control charger off** – the plan keeps running and `binary_sensor.*_charge_now`
  stays up to date, but nothing is sent. Use this for a combination where another
  controller (for example a solar/battery app) reads *Charge now* as a "grid charge
  wanted" request.

## Flaky Wi-Fi chargers

Commands are retried (10 s, 20 s, 30 s, then every minute) until the charger reports
the wanted state, and the controller waits for an offline charger to come back
(up to 2 h). The `charger_command` sensor shows *Retrying* or *Charger offline*.

### Garo wallboxes: write the plan into the box

With the [garo_wallbox](https://github.com/sockless-coding/garo_wallbox) integration,
Simple Charge can also write the plan into the box's own weekly schedule
(Fine tuning → *Garo schedule sensor*, then turn on *Write Garo schedule*). When the
box is in `SCHEMA` mode it then charges at the planned times even if Home Assistant
cannot reach it. Notes:

- Simple Charge owns the whole box schedule while this is on: entries it did not
  plan are removed.
- Entries are removed again as soon as their time has passed, because the Garo
  schedule repeats every week. Nothing is written more than 6 days ahead.
- Use the select control with `ALWAYS_ON` (charge) and `SCHEMA` (stop) so the
  schedule is active whenever Simple Charge is not forcing a charge.

## Dashboard example

```yaml
type: entities
title: Car charging
entities:
  - entity: select.simple_charge_mode
  - entity: sensor.simple_charge_status
  - entity: sensor.simple_charge_plan
  - entity: number.simple_charge_charging_time
  - entity: number.simple_charge_max_price
  - entity: number.simple_charge_relative_limit
  - entity: switch.simple_charge_ready_by
  - entity: datetime.simple_charge_ready_by_time
  - entity: binary_sensor.simple_charge_charge_now
```

## Migrating from a template sensor (version 1)

Version 1 of this idea was a template `binary_sensor` plus two automations. To move:

1. Set up Simple Charge with the same price sensors and copy your values:
   charging hours → *Charging time*, fixed threshold → *Max price*, the share of the
   recent average (for example `* 0.5`) → *Relative limit* `50 %`, the average sensor
   → *Reference average price*.
2. Turn off the old automations, then remove the old template sensor.
3. If other automations read the old binary sensor, either point them at
   `binary_sensor.<name>_charge_now` or rename the new entity to the old entity id
   (Settings → Entities → the entity → ⚙ → Entity ID).

## Roadmap

- Several cars (which car is plugged in) with their own battery size and target.
- Charging power from the charger itself to fine-tune the needed time.
- Optional "prefer one long block" to avoid many short start/stops.

## Development

```bash
python -m venv .venv && .venv/bin/pip install pytest pillow ruff
.venv/bin/python -m pytest          # planner and price parsing, no Home Assistant needed
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python scripts/make_brand.py   # redraw the logo
```

Releases: bump `version` in `manifest.json`, add a `CHANGELOG.md` entry, push a tag
`vX.Y.Z`. The release workflow publishes the GitHub release that HACS reads.

## License

Apache License 2.0, see [LICENSE](LICENSE).
