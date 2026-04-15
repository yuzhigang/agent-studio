import os
import pytest
from src.runtime.model_loader import ModelLoader, ModelConfigError

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "agents")

def test_load_legacy_model_yaml():
    result = ModelLoader.load(os.path.join(FIXTURES, "legacy_agent"))
    assert result["metadata"]["name"] == "legacy_agent"
    assert result["variables"]["temperature"]["default"] == 25.0

def test_load_legacy_model_json():
    result = ModelLoader.load(os.path.join(FIXTURES, "legacy_json_agent"))
    assert result["metadata"]["name"] == "legacy_json_agent"
    assert result["attributes"]["power"]["default"] == 100
