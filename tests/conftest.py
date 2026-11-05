"""Load the pure modules (planner, prices) without Home Assistant installed."""

import importlib.util
from pathlib import Path
import sys
import types

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "simple_charge"

package = types.ModuleType("simple_charge")
package.__path__ = [str(PKG_DIR)]
sys.modules.setdefault("simple_charge", package)

for name in ("planner", "prices"):
    spec = importlib.util.spec_from_file_location(f"simple_charge.{name}", PKG_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"simple_charge.{name}"] = module
    spec.loader.exec_module(module)
