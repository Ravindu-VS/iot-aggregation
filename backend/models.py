from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NormalizedPayload:
    """Normalized sensor payload with node identification and metrics."""
    sensor_id: str
    node_id: str
    metrics: dict[str, float] = field(default_factory=dict)
    values: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class SensorSummary:
    """Summary statistics for a single value list."""
    min_value: float
    max_value: float
    avg_value: float
    count: int

    def to_dict(self) -> dict:
        """Convert summary to dictionary."""
        return {
            "min": self.min_value,
            "max": self.max_value,
            "avg": self.avg_value,
            "count": self.count,
        }


@dataclass(frozen=True)
class MetricSummary:
    """Summary statistics for individual metrics with time windows."""
    node_id: str
    metric_name: str
    latest: float
    min_value: float
    max_value: float
    avg_value: float
    count: int
    
    def to_dict(self) -> dict:
        """Convert metric summary to dictionary."""
        return {
            "node_id": self.node_id,
            "metric": self.metric_name,
            "latest": self.latest,
            "min": self.min_value,
            "max": self.max_value,
            "avg": self.avg_value,
            "count": self.count,
        }


def generate_object_key(sensor_id: str, data_id: str) -> str:
   
    return f"raw/{sensor_id}/{data_id}.json"
