# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub:
**Security → Report a vulnerability** on this repository
(private vulnerability reporting). Do not open a public issue.

You can expect a first answer within a week.

## Scope

Simple Charge runs inside Home Assistant, has no network services of its own
and stores no credentials. It only calls Home Assistant actions on entities you
choose during setup (your charger switch/select/scripts and, optionally, the
`garo_wallbox` schedule actions).

## Supported versions

Only the latest release gets fixes.
