# Observability E2E

> **第一版实现（含后续维护版本），仅保留供评估。第二版不一定需要，是否复用必须由对应负责人确认。**
> **第二版采用状态：待确认。** 未确认前，不列为必做功能，不默认接入或部署，不以其旧接口约束新 APK。
> 这里的“第一版”指产品代际，不是把包版本改为 1.0；版本来源及职责见 [当前模块清单](../REGISTRY.md)。

Version `0.2.0` defines canonical cross-device sources and operation stages.
Reports automatically calculate planning, rendering, sync, scheduling,
transition and resume timings needed by the 12-second, 15-second and RK timing
acceptance gates.

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
