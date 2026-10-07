from app.main import app
from scripts.rag_runtime_check import REQUIRED_PATHS


def test_required_runtime_contract_paths_are_registered():
    registered_paths = {route.path for route in app.routes}
    missing = [path for path in REQUIRED_PATHS if path not in registered_paths]
    assert missing == []
