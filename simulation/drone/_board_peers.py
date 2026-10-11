"""The flight controller board's part models from the sim-fixtures checkout (PALMPILOT_DRONE_BOARD)."""
import importlib.util
import os


def load(name):
    path = os.path.join(os.environ["PALMPILOT_DRONE_BOARD"], "peers", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"board_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
