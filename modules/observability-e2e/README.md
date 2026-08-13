# Observability E2E

This module provides the evidence layer required before HarBeat runtime code is
extracted or deleted. It does not plan transitions, render audio, synchronize
assets, or control playback by itself.

## Responsibilities

- Inventory code and configuration without copying private runtime data.
- Locate Flutter controls from the current UTF-8 UIAutomator frame.
- Normalize mobile, Jetson, and RK events into one operation timeline.
- Produce machine-readable reports with secret redaction.

## Safety

The inventory scanner excludes caches, databases, media, models, virtual
environments, Git objects, build output, logs, and common secret files by
default. It only reads files and emits metadata and SHA256 hashes.

The repository must not contain production APKs, user preferences, tokens,
music, stems, renders, databases, model weights, or complete device backups.

## Tests

```powershell
py -m unittest discover modules/observability-e2e/tests -v
```

## Local Inventory

```powershell
py modules/observability-e2e/src/harbeat_observability/cli.py inventory `
  --root D:\work\harbeat-client `
  --output reports/baselines/workspace-source-inventory.json
```

## UI Lookup

```powershell
adb -s 130ddcca shell uiautomator dump /sdcard/harbeat-ui.xml
adb -s 130ddcca pull /sdcard/harbeat-ui.xml tmp/harbeat-ui.xml
py modules/observability-e2e/src/harbeat_observability/cli.py find-control `
  --xml tmp/harbeat-ui.xml `
  --label "确认切歌"
```

The command returns the current control bounds and center. A caller must dump a
fresh frame immediately before tapping; stored coordinates are not reusable.
