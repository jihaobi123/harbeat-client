"""Patch jetson router: add ?style= param to energy endpoint, prefer v2.

Run on jetson:
    /home/mark/venvs/harbeat/bin/python /tmp/router_energy_v2_patch.py
"""
import re
from pathlib import Path

p = Path("/home/mark/harbeat/app/modules/dj_control/router.py")
src = p.read_text(encoding="utf-8")

# Add import for v2 module if absent
if "energy_streetdance" not in src:
    src = src.replace(
        "from app.modules.dj_control.energy_hiphop import compute_dance_energy",
        "from app.modules.dj_control.energy_hiphop import compute_dance_energy\n"
        "from app.modules.dj_control.energy_streetdance import (\n"
        "    compute_street_energy,\n"
        "    list_buckets,\n"
        "    list_style_profiles,\n"
        "    STREET_ENERGY_PROFILES,\n"
        ")",
        1,
    )

new_endpoint = '''@router.get("/songs/{song_id}/energy")
def energy_breakdown_endpoint(
    song_id: str,
    style: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Energy breakdown.

    style param:
      - omitted (None)  -> v1 compute_dance_energy (legacy behaviour preserved)
      - any of {breaking, hiphop, popping, locking, house, krump, waacking, generic}
                        -> v2 compute_street_energy (style-aware)

    For songs without music_features.dj fingerprint, v2 returns total=0
    bucket=cold style_used=no_dj — caller can fall back to v1 if desired.
    """
    song = db.get(LibrarySong, song_id)
    if not song or song.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="song not found")
    if style is None:
        # legacy v1 path (kept 90 days for parity)
        eb = compute_dance_energy(song)
        return APIResponse(data={"version": "v1", **eb.as_dict()})
    style_norm = style.lower()
    if style_norm not in STREET_ENERGY_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown style: {style}. valid: {sorted(STREET_ENERGY_PROFILES.keys())}",
        )
    se = compute_street_energy(song, style=style_norm)
    return APIResponse(data={"version": "v2", **se.as_dict()})


@router.get("/energy/buckets")
def list_energy_buckets_endpoint():
    """5-bucket schema for UI rendering of energy chips/colors."""
    return APIResponse(data={"buckets": list_buckets()})


@router.get("/energy/profiles")
def list_energy_profiles_endpoint():
    """Per-style weight tables — useful for debug / UI sliders."""
    return APIResponse(data={"profiles": list_style_profiles()})'''

src = re.sub(
    r'@router\.get\("/songs/\{song_id\}/energy"\)\ndef energy_breakdown_endpoint\(.*?return APIResponse\(data=eb\.as_dict\(\)\)',
    new_endpoint,
    src,
    count=1,
    flags=re.DOTALL,
)

p.write_text(src, encoding="utf-8")
print("router patched ->", p)
