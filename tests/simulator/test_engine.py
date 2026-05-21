import pytest
from unittest.mock import patch, AsyncMock
from src.simulator.engine import EventSimulator
from src.simulator.config import SimulatorConfig, SourceConfig


@pytest.mark.anyio
async def test_engine_runs_and_stops():
    cfg = SimulatorConfig(
        supervisor_url="http://localhost:8080",
        sources=[SourceConfig(name="s1", target_world="demo-world", schedule=[])]
    )
    sim = EventSimulator(cfg)
    with patch.object(sim._scheduler, "start", new_callable=AsyncMock) as mock_start, \
         patch.object(sim._scheduler, "stop", new_callable=AsyncMock) as mock_stop:
        # Trigger shutdown immediately
        sim._shutdown_event.set()
        await sim.run()
        mock_start.assert_awaited_once()
        mock_stop.assert_awaited_once()
