from typing import Protocol

from domain.config.matrix import Matrix
from domain.config.thresholds import Thresholds
from domain.geo import DistanceUnit
from domain.types import TestID


class Config(Protocol):
    """Config provides persistent app configuration"""

    @property
    def test_id(self) -> TestID:
        """ID of the test to display data matrix for"""
        pass

    @property
    def data_update_period_seconds(self) -> int:
        """Minimal time period between test results cache updates"""
        pass

    @property
    def data_update_lookback_seconds(self) -> int:
        """Time window to fetch the test results for"""
        pass

    @property
    def latency(self) -> Thresholds:
        """Latency thresholds, in milliseconds"""
        pass

    @property
    def jitter(self) -> Thresholds:
        """Jitter thresholds, in milliseconds"""
        pass

    @property
    def packet_loss(self) -> Thresholds:
        """Packet loss thresholds, in percents (0-100)"""
        pass

    @property
    def matrix(self) -> Matrix:
        """Matrix cell colors"""
        pass

    @property
    def distance_unit(self) -> DistanceUnit:
        """Unit for distance between agents"""
        pass
