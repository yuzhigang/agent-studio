from dataclasses import dataclass, field
from typing import Any
import yaml


@dataclass
class ScheduleItem:
    event: str
    every: str
    jitter: str = "0s"
    payload: dict = field(default_factory=dict)


@dataclass
class SourceConfig:
    name: str
    target_world: str
    schedule: list[ScheduleItem] = field(default_factory=list)
    script: str = ""


@dataclass
class SimulatorConfig:
    supervisor_url: str
    sources: list[SourceConfig]


def _parse_duration(s: str) -> float:
    """Parse duration string like '2s', '100ms', '1m' to seconds."""
    s = s.strip()
    if s.endswith("ms"):
        return float(s[:-2]) / 1000
    elif s.endswith("s"):
        return float(s[:-1])
    elif s.endswith("m"):
        return float(s[:-1]) * 60
    else:
        return float(s)


def load_config(path: str) -> SimulatorConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    sources = []
    for s in raw.get("sources", []):
        schedule = []
        for item in s.get("schedule", []):
            schedule.append(ScheduleItem(
                event=item["event"],
                every=item["every"],
                jitter=item.get("jitter", "0s"),
                payload=item.get("payload", {})
            ))
        sources.append(SourceConfig(
            name=s["name"],
            target_world=s["target_world"],
            schedule=schedule,
            script=s.get("script", "")
        ))
    return SimulatorConfig(
        supervisor_url=raw["supervisor_url"],
        sources=sources
    )
