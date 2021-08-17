from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

MetricValue = float
""" latency and jitter in milliseconds, packet_loss in percent (0-100) """


class MetricUnit(Enum):
    """Measurement units for mesh test metrics"""

    LATENCY = "ms"
    JITTER = "ms"
    PACKET_LOSS = "%"


class MetricType(Enum):
    """Available mesh test metric types"""

    LATENCY = "Latency"
    JITTER = "Jitter"
    PACKET_LOSS = "Packet loss"

    @property
    def unit(self) -> str:
        return MetricUnit.__getattr__(self.name).value  # type: ignore


@dataclass
class Metric:
    """Representation of single test metric"""

    type: MetricType
    value: MetricValue

    @property
    def unit(self) -> str:
        return self.type.unit
