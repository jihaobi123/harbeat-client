import sys
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "edge-agent"))


def test_transition_plan_router_is_registered_on_edge_agent_app():
    spec = importlib.util.spec_from_file_location("edge_agent_main_for_test", ROOT / "edge-agent" / "main.py")
    main = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(main)

    route_paths = {getattr(route, "path", "") for route in main.app.routes}

    assert "/transition/plan" in route_paths
