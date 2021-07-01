import logging
from typing import Tuple

import yaml

from domain.config import Matrix
from domain.geo import DistanceUnit
from domain.types import TestID
from infrastructure.config.thresholds import Thresholds


class ConfigYAML:
    """ ConfigYAML implements domain.config.config.Config protocol """

    @property
    def test_id(self) -> TestID:
        return self._test_id

    @property
    def data_update_period_seconds(self) -> int:
        return self._data_update_seconds

    @property
    def data_update_lookback_seconds(self) -> int:
        return self._data_update_lookback_seconds

    @property
    def latency(self) -> Thresholds:
        return self._latency

    @property
    def jitter(self) -> Thresholds:
        return self._jitter

    @property
    def packet_loss(self) -> Thresholds:
        return self._packet_loss

    @property
    def timeout(self) -> Tuple[float, float]:
        return self._timeout  # type: ignore

    @property
    def logging_level(self) -> int:
        return self._logging_level

    @property
    def matrix(self) -> Matrix:
        return self._matrix

    @property
    def distance_unit(self) -> DistanceUnit:
        return self._distance_unit

    def __init__(self, filename: str) -> None:
        try:
            with open(filename, "r") as file:
                config = yaml.load(file, yaml.SafeLoader)

            self._test_id = TestID(config["test_id"])
            self._data_update_seconds = int(config["data_update_period_seconds"])
            self._data_update_lookback_seconds = int(config["data_update_lookback_seconds"])
            self._latency = Thresholds(config["thresholds"]["latency"])
            self._jitter = Thresholds(config["thresholds"]["jitter"])
            self._packet_loss = Thresholds(config["thresholds"]["packet_loss"])
            self._timeout = tuple(config["timeout"])
            self._logging_level = self._parse_logging_level(config)
            self._matrix = Matrix(
                config["matrix"]["cell_color_healthy"],
                config["matrix"]["cell_color_warning"],
                config["matrix"]["cell_color_critical"],
                config["matrix"]["cell_color_nodata"],
            )
            self._distance_unit = DistanceUnit(config["distance_unit"])
        except Exception as err:
            raise Exception("Configuration error") from err

    def _parse_logging_level(self, config) -> int:
        try:
            if config["logging_level"] == "FATAL" or config["logging_level"] == "CRITICAL":
                return logging.CRITICAL
            if config["logging_level"] == "ERROR":
                return logging.ERROR
            if config["logging_level"] == "WARN" or config["logging_level"] == "WARNING":
                return logging.WARNING
            if config["logging_level"] == "INFO":
                return logging.INFO
            if config["logging_level"] == "DEBUG":
                return logging.DEBUG
            else:
                raise ValueError(f"{config['logging_level']} is not defined")
        except KeyError:
            return logging.INFO
