"""Verify source-only snapshots; does not load models or read private audio."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1]
source=root/'services/preprocessing'
inventory=json.loads((source/'SOURCE_INVENTORY.json').read_text())
for relative,expected in inventory['files'].items():
    path=source/relative
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise SystemExit('Preprocessing source changed: '+relative)
frozen={
    'algorithm_demo_transition_logic_1_0.py':'8cf342e72a688ccde658cf402866f63f3cc7fe8eafd7fc70857cc32d6185069a',
    'mix_plan.json':'686ab054ceac986d508c85271aef2fb7934c95bfa168fe9c1423793ee1e0a14b',
}
for name,expected in frozen.items():
    path=root/'mixing/vendor/colleague_demo_v1'/name
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise SystemExit('Frozen V3 changed: '+name)
print(f"Verified {len(inventory['files'])} deployed source files and frozen V3 renderer/plan")
