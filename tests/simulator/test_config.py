import pytest
from src.simulator.config import load_config, _parse_duration


def test_parse_duration():
    assert _parse_duration("2s") == 2.0
    assert _parse_duration("500ms") == 0.5
    assert _parse_duration("1m") == 60.0


def test_load_minimal_config(tmp_path):
    config_path = tmp_path / "sim.yaml"
    config_path.write_text("""
supervisor_url: http://localhost:8080
sources:
  - name: sensor
    target_world: demo-world
    schedule:
      - event: beat
        every: 2s
""")
    cfg = load_config(str(config_path))
    assert cfg.supervisor_url == "http://localhost:8080"
    assert len(cfg.sources) == 1
    assert cfg.sources[0].name == "sensor"
    assert len(cfg.sources[0].schedule) == 1
    assert cfg.sources[0].schedule[0].event == "beat"
