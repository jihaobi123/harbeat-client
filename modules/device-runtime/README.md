# Device Runtime

This module is the device-side contract for mobile-to-RK control. It keeps the
device identity stable while allowing the hotspot address to change.

## Responsibilities

- Normalize an entered or discovered RK URL.
- Identify a device by its stable `device_id`, never by its IP address.
- Keep a short-lived connection/session record.
- Parse `/health` and `/state` into bounded DTOs.
- Represent a manual operation with a compact reference only.
- Classify transient timeout, unreachable, stale-session, and protocol errors.

## Deliberate non-responsibilities

This module does not select songs, plan transitions, render WAV files, sync
assets, schedule playback, or store a complete render plan. Those belong to
separate modules.

## Contract rules

1. An IP/port is an endpoint, not device identity.
2. A changed endpoint may reconnect to the same device only after `/health`
   reports the expected `device_id`.
3. A session is invalidated after its TTL or when the device reports a new
   session. Old operation references must not be reused.
4. An operation reference contains IDs and deadlines, never audio data or a
   complete plan.
5. A temporary network error is recoverable; a device mismatch or malformed
   response is a hard failure.

## Tests

```powershell
py -m unittest discover modules/device-runtime/tests -v
```

The implementation is standard-library-only so it can be tested from a fresh
clone without installing the production mobile or RK environments.

## Read-only deployed probe

```powershell
py modules/device-runtime/src/harbeat_device_runtime/cli.py `
  http://127.0.0.1:19000 `
  --output reports/device-runtime-probe.json
```

The report intentionally excludes the current song ID, session ID, sync URLs,
tokens, render plans, and audio paths.
