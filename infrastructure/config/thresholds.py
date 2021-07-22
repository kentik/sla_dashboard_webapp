from dataclasses import dataclass
from typing import Any, Dict, Optional

from domain.types import AgentID, Threshold


@dataclass
class ThresholdOverride:
    """Threshold overrides can be optionally specified; if not specified - default values shall be used"""

    warning: Optional[Threshold] = None
    critical: Optional[Threshold] = None


class Thresholds:
    """
    Thresholds allow to read threshold values for given agent pair based on configuration.
    It implements domain.config.thresholds.Thresholds protocol
    """

    def warning(self, from_agent: AgentID, to_agent: AgentID) -> Threshold:
        override = self._get_override_or_none(from_agent, to_agent)
        if override is None or override.warning is None:
            return self._default_warning
        return override.warning

    def critical(self, from_agent: AgentID, to_agent: AgentID) -> Threshold:
        override = self._get_override_or_none(from_agent, to_agent)
        if override is None or override.critical is None:
            return self._default_critical
        return override.critical

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Example of config dict structure for thresholds:
        "defaults":{
            "warning":200.0,
            "critical":400.0
        },
        "overrides":[
            {
            "from":10,
            "to":11,
            "warning":10.0,
            "critical":20.0
            },
            {
            "from":60,
            "to":70,
            "warning":1000.0,
            "critical":2000.0
            }
        ]
        """
        try:
            # read defaults config (required)
            self._default_warning = Threshold(config["defaults"]["warning"])
            self._default_critical = Threshold(config["defaults"]["critical"])

            # read overrides config (optional)
            self._overrides: Dict[AgentID, Dict[AgentID, ThresholdOverride]] = dict()
            if "overrides" not in config:
                return

            for override in config["overrides"]:
                from_agent = AgentID(override["from"])
                to_agent = AgentID(override["to"])
                if "warning" in override:
                    self._override_warning(from_agent, to_agent, Threshold(override["warning"]))
                if "critical" in override:
                    self._override_critical(from_agent, to_agent, Threshold(override["critical"]))
        except KeyError as err:
            raise Exception("Incomplete thresholds definition") from err

    def _override_warning(self, from_agent: AgentID, to_agent: AgentID, value: Threshold) -> None:
        override = self._get_or_create_override(from_agent, to_agent)
        override.warning = value

    def _override_critical(self, from_agent: AgentID, to_agent: AgentID, value: Threshold) -> None:
        override = self._get_or_create_override(from_agent, to_agent)
        override.critical = value

    def _get_or_create_override(self, from_agent: AgentID, to_agent: AgentID) -> ThresholdOverride:
        overrides = self._overrides
        if from_agent not in overrides:
            overrides[from_agent] = dict()
        if to_agent not in overrides[from_agent]:
            overrides[from_agent][to_agent] = ThresholdOverride()
        return overrides[from_agent][to_agent]

    def _get_override_or_none(self, from_agent: AgentID, to_agent: AgentID) -> Optional[ThresholdOverride]:
        overrides = self._overrides
        if from_agent not in overrides:
            return None
        if to_agent not in overrides[from_agent]:
            return None
        return overrides[from_agent][to_agent]
