from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

_source = Path(__file__).parents[1] / "clean-environment" / "harbeatctl.py"
_spec = spec_from_file_location("harbeatctl_impl", _source)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load {_source}")
_module = module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
main = _module.main
validate = _module.validate
