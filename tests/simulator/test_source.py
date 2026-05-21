import pytest
from unittest.mock import AsyncMock
from src.simulator.source import SimSource
from src.simulator.config import SourceConfig, ScheduleItem


@pytest.mark.anyio
async def test_source_generates_gaussian_payload():
    poster = AsyncMock()
    cfg = SourceConfig(
        name="test",
        target_world="demo-world",
        schedule=[ScheduleItem(event="tick", every="1s", payload={
            "temperature": {"type": "gaussian", "mean": 60, "std": 20}
        })]
    )
    source = SimSource(cfg, poster)
    item = cfg.schedule[0]
    event = source._generate_event(item)
    assert event.event_type == "tick"
    assert isinstance(event.payload["temperature"], float)


@pytest.mark.anyio
async def test_source_generates_uniform_payload():
    poster = AsyncMock()
    cfg = SourceConfig(
        name="test",
        target_world="demo-world",
        schedule=[ScheduleItem(event="tick", every="1s", payload={
            "pressure": {"type": "uniform", "min": 100, "max": 200}
        })]
    )
    source = SimSource(cfg, poster)
    item = cfg.schedule[0]
    event = source._generate_event(item)
    assert 100 <= event.payload["pressure"] <= 200


@pytest.mark.anyio
async def test_source_generates_exponential_payload():
    poster = AsyncMock()
    cfg = SourceConfig(
        name="test",
        target_world="demo-world",
        schedule=[ScheduleItem(event="tick", every="1s", payload={
            "delay": {"type": "exponential", "rate": 0.5}
        })]
    )
    source = SimSource(cfg, poster)
    item = cfg.schedule[0]
    event = source._generate_event(item)
    assert event.payload["delay"] >= 0


@pytest.mark.anyio
async def test_source_generates_triangular_payload():
    poster = AsyncMock()
    cfg = SourceConfig(
        name="test",
        target_world="demo-world",
        schedule=[ScheduleItem(event="tick", every="1s", payload={
            "load": {"type": "triangular", "low": 0, "high": 100, "mode": 50}
        })]
    )
    source = SimSource(cfg, poster)
    item = cfg.schedule[0]
    event = source._generate_event(item)
    assert 0 <= event.payload["load"] <= 100


@pytest.mark.anyio
async def test_source_generates_lognormal_payload():
    poster = AsyncMock()
    cfg = SourceConfig(
        name="test",
        target_world="demo-world",
        schedule=[ScheduleItem(event="tick", every="1s", payload={
            "latency": {"type": "lognormal", "mu": 0, "sigma": 1}
        })]
    )
    source = SimSource(cfg, poster)
    item = cfg.schedule[0]
    event = source._generate_event(item)
    assert event.payload["latency"] > 0


@pytest.mark.anyio
async def test_source_generates_pareto_payload():
    poster = AsyncMock()
    cfg = SourceConfig(
        name="test",
        target_world="demo-world",
        schedule=[ScheduleItem(event="tick", every="1s", payload={
            "size": {"type": "pareto", "alpha": 1.0}
        })]
    )
    source = SimSource(cfg, poster)
    item = cfg.schedule[0]
    event = source._generate_event(item)
    assert event.payload["size"] >= 1


@pytest.mark.anyio
async def test_source_generates_weibull_payload():
    poster = AsyncMock()
    cfg = SourceConfig(
        name="test",
        target_world="demo-world",
        schedule=[ScheduleItem(event="tick", every="1s", payload={
            "lifetime": {"type": "weibull", "alpha": 1.0, "beta": 1.0}
        })]
    )
    source = SimSource(cfg, poster)
    item = cfg.schedule[0]
    event = source._generate_event(item)
    assert event.payload["lifetime"] >= 0


@pytest.mark.anyio
async def test_source_generates_static_payload():
    poster = AsyncMock()
    cfg = SourceConfig(
        name="test",
        target_world="demo-world",
        schedule=[ScheduleItem(event="beat", every="1s", payload={
            "status": "alive",
            "count": {"type": "static", "value": 42}
        })]
    )
    source = SimSource(cfg, poster)
    item = cfg.schedule[0]
    event = source._generate_event(item)
    assert event.payload["status"] == "alive"
    assert event.payload["count"] == 42
