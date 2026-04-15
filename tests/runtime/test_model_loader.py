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

def test_load_split_model_directory():
    result = ModelLoader.load(os.path.join(FIXTURES, "split_agent"))
    assert result["metadata"]["name"] == "split_agent"
    assert result["variables"]["speed"]["default"] == 10
    assert "capacityLimit" in result["rules"]
    assert "onEnterFull" in result["behaviors"]

def test_missing_index_yaml_raises():
    with pytest.raises(ModelConfigError, match="requires index.yaml"):
        ModelLoader.load(os.path.join(FIXTURES, "bad_split_agent"))

def test_missing_model_raises():
    with pytest.raises(ModelConfigError, match="Agent path does not exist"):
        ModelLoader.load(os.path.join(FIXTURES, "nonexistent_agent"))

def test_invalid_yaml_raises():
    with pytest.raises(ModelConfigError, match="YAML parse error"):
        ModelLoader.load(os.path.join(FIXTURES, "bad_yaml_agent"))
