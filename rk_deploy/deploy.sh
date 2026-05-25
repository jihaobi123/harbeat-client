#!/bin/bash
# HarBeat Live DJ Control — RK3588 Deploy Script
# Run when RK is online: bash rk_deploy/deploy.sh
#
# This script:
# 1. Copies new Python modules to edge-agent
# 2. Patches main.py to extend /state + register live routes
# 3. Patches models.py to add TransitionDetail + extend RKPlaybackState
# 4. Restarts edge-agent service

set -e

RK_USER="cat"
RK_HOST="192.168.5.17"
RK_EDGE="/home/cat/cypher/edge-agent/edge_agent"
RK_MAIN="/home/cat/cypher/edge-agent/main.py"
RK_MODELS="/home/cat/cypher/edge-agent/edge_agent/models.py"

echo "=== HarBeat Live Control Deploy ==="

# 1. Copy new modules
echo "[1/4] Copying live_api.py and live_models.py..."
scp rk_deploy/live_models.py ${RK_USER}@${RK_HOST}:${RK_EDGE}/live_models.py
scp rk_deploy/live_api.py ${RK_USER}@${RK_HOST}:${RK_EDGE}/live_api.py

# 2. Patch models.py
echo "[2/4] Patching models.py..."
ssh ${RK_USER}@${RK_HOST} << 'ENDSSH'
cd /home/cat/cypher/edge-agent/edge_agent

# Add TransitionDetail to models.py if not present
if ! grep -q "class TransitionDetail" models.py; then
  cat >> models.py << 'EOF'

# ── Live DJ Control (added by deploy script) ─────────────────────

class TransitionDetail(BaseModel):
    to_song_id: str = ""
    style: str = "blend"
    starts_in_sec: float = 0.0
    confidence: float = 0.0
    tags: list[str] = Field(default_factory=list)

class LiveOverrideRequest(BaseModel):
    next_song_id: str | None = None
    style: str | None = None
    fade_sec: float | None = Field(default=None, ge=0.5, le=30.0)
    execute: Literal["now", "next_beat", "next_bar", "next_phrase"] = "next_phrase"

class LiveOverrideResponse(BaseModel):
    ok: bool = True
    transition: TransitionDetail = Field(default_factory=TransitionDetail)
    warnings: list[str] = Field(default_factory=list)

class LiveIntentRequest(BaseModel):
    intent: Literal[
        "energy_up", "energy_down", "hold_energy", "drop_now",
        "cooldown", "smoother", "harder", "safer",
        "vocal_safe", "instrumental",
    ]
    scope: Literal["next_transition", "next_3"] = "next_transition"
    max_risk: float = Field(default=0.45, ge=0.0, le=1.0)

class LiveIntentResponse(BaseModel):
    ok: bool = True
    updated_plan: dict[str, Any] | None = None
    explanation: str | None = None
    warnings: list[str] = Field(default_factory=list)
EOF
  echo "  models.py patched."
else
  echo "  models.py already patched — skipping."
fi
ENDSSH

# 3. Patch main.py
echo "[3/4] Patching main.py..."
ssh ${RK_USER}@${RK_HOST} << 'ENDSSH'
MAIN="/home/cat/cypher/edge-agent/main.py"

# Add live_router import and registration if not present
if ! grep -q "live_api" "$MAIN"; then
  # Add import after transition_api import
  sed -i 's/from edge_agent.transition_api import router as transition_router/from edge_agent.transition_api import router as transition_router\nfrom edge_agent.live_api import router as live_router/' "$MAIN"

  # Register live_router after transition_router
  sed -i 's/app.include_router(transition_router)/app.include_router(transition_router)\napp.include_router(live_router)/' "$MAIN"

  echo "  main.py patched with live_api imports."
else
  echo "  main.py already patched — skipping."
fi

# Extend /state endpoint to include current_section, current_energy, next_transition
if ! grep -q "current_section" "$MAIN"; then
  # Replace the get_state function
  python3 << 'PYEOF'
import re

with open("/home/cat/cypher/edge-agent/main.py") as f:
    content = f.read()

old_get_state = '''@app.get("/state", response_model=RKPlaybackState)
async def get_state() -> RKPlaybackState:
  try:
    state = audio_client.send_command({"cmd": "state"}, timeout=1.0)
    if state.get("ok") is not False:
      await edge_state.set_audio_ready(True)
      return await edge_state.replace_playback_from_audio(state)
  except AudioEngineError:
    await edge_state.set_audio_ready(False)
  return await edge_state.snapshot_playback()'''

new_get_state = '''@app.get("/state", response_model=RKPlaybackState)
async def get_state() -> RKPlaybackState:
  try:
    state = audio_client.send_command({"cmd": "state"}, timeout=1.0)
    if state.get("ok") is not False:
      await edge_state.set_audio_ready(True)
      playback = await edge_state.replace_playback_from_audio(state)

      # ── Live DJ: enrich with section/energy/transition detail ──
      from edge_agent.live_api import (
          _find_current_section, _get_current_energy, _build_transition_detail,
      )
      current_id = str(playback.current_song_id) if playback.current_song_id else None
      pos = playback.position_sec

      section = _find_current_section(current_id, pos)
      energy_val = _get_current_energy(current_id)

      next_detail = None
      if playback.next_song_id and playback.next_transition_in_sec:
          next_detail = _build_transition_detail(
              str(playback.next_song_id),
              "blend",
              playback.next_transition_in_sec,
          )

      # Merge enriched fields into response
      enriched = playback.model_dump()
      enriched["current_section"] = section
      enriched["current_energy"] = energy_val
      if next_detail:
          enriched["next_transition"] = next_detail.model_dump()

      return RKPlaybackState(**{k: v for k, v in enriched.items()
                                if k in RKPlaybackState.model_fields})

  except AudioEngineError:
    await edge_state.set_audio_ready(False)
  return await edge_state.snapshot_playback()'''

content = content.replace(old_get_state, new_get_state)

with open("/home/cat/cypher/edge-agent/main.py", "w") as f:
    f.write(content)

print("  /state endpoint enriched with section, energy, next_transition.")
PYEOF
  echo "  main.py /state endpoint enriched."
else
  echo "  /state already enriched — skipping."
fi
ENDSSH

# 4. Restart edge-agent
echo "[4/4] Restarting edge-agent..."
ssh ${RK_USER}@${RK_HOST} "sudo systemctl restart cypher-edge-agent" 2>/dev/null || \
  ssh ${RK_USER}@${RK_HOST} "pkill -f 'edge-agent' && sleep 1 && cd /home/cat/cypher/edge-agent && nohup python3 main.py > /tmp/edge-agent.log 2>&1 &" 2>/dev/null || \
  echo "  WARNING: could not restart edge-agent. Please restart manually."

echo ""
echo "=== Deploy Complete ==="
echo "Verify:"
echo "  curl http://${RK_HOST}:9000/state | jq '.current_section, .current_energy, .next_transition'"
echo "  curl -X POST http://${RK_HOST}:9000/live/intent -H 'Content-Type: application/json' -d '{\"intent\":\"energy_up\"}'"
echo "  curl -X POST http://${RK_HOST}:9000/live/override -H 'Content-Type: application/json' -d '{\"style\":\"bass_swap\",\"execute\":\"next_bar\"}'"
