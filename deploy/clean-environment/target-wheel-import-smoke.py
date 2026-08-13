#!/usr/bin/env python3
import json
import platform

import harbeat_asset_sync
import harbeat_audio_preprocess
import harbeat_audio_runtime
import harbeat_device_runtime
import harbeat_library_catalog
import harbeat_observability
import harbeat_physical_input
import harbeat_sequence_planner
import harbeat_stem_separation
import harbeat_transition_orchestrator
import harbeat_transition_planner
import harbeat_transition_renderer


print(json.dumps({
    "python": platform.python_version(),
    "architecture": platform.machine(),
    "wheel_imports": "12/12",
}, sort_keys=True))
