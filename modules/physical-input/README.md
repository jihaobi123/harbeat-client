# Physical Input

Version `0.2.0` separates immutable key-routing rules (`domain.py`) from the
RK audio socket wire adapter (`protocol.py`). `routing.py` is a named v0.1
compatibility facade and contains no duplicate behavior.

This module records the real MYKB E9s button semantics without requiring a
keyboard, RK, Unix socket, or mixer during tests.

| Logical key | Action |
|---|---|
| 1-5 | Trigger the same audio-engine SFX key and report `key_event` |
| 6 | Trigger audio sample 3 (vinyl stop) and report logical key 6 |
| 0 | Trigger audio key 0 (pause/resume) and report `key_event` |
| 7-9 | Report navigation `key_event` only |
| Volume up/down | Adjust RK PCM by 5% and report `key_event` |

The deployed daemon currently defines `KEY_MAP` twice with identical content;
the extracted core has one authoritative routing table. More importantly,
the current mobile client does not consume RK key events for keys 7-9, so
those three physical navigation buttons are not yet end-to-end DJ controls.

## Test

```powershell
$env:PYTHONPATH = "modules/physical-input/src"
py -m pytest -q modules/physical-input/tests
```
