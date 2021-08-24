from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Generator, List, Optional, Tuple

from domain.geo import Coordinates
from domain.metric import Metric, MetricType, MetricValue
from domain.types import AgentID

logger = logging.getLogger(__name__)


@dataclass
class Agent:
    id: AgentID = AgentID()
    ip: str = ""
    name: str = ""
    alias: str = ""
    coords: Coordinates = Coordinates()


class Agents:
    def __init__(self) -> None:
        self._agents: Dict[AgentID, Agent] = {}
        self._agents_by_name: Dict[str, Agent] = {}

    def equals(self, other: Agents) -> bool:
        return self._agents == other._agents

    def get_by_id(self, agent_id: AgentID) -> Agent:
        return self._agents.get(agent_id, Agent())

    def get_by_name(self, name: str) -> Agent:
        return self._agents_by_name.get(name, Agent())

    def insert(self, agent: Agent) -> None:
        self._agents[agent.id] = agent
        existing = self._agents_by_name.get(agent.name)
        if existing:
            logger.warning("Duplicate agent name '%s' (ids: %s %s)", agent.name, existing.id, agent.id)
            _dedup_name = "{agent.name} [{agent.id}]"
            del self._agents_by_name[existing.name]
            existing.name = _dedup_name.format(agent=existing)
            self._agents_by_name[existing.name] = existing
            agent.name = _dedup_name.format(agent=agent)
        self._agents_by_name[agent.name] = agent
        logger.debug("adding agent: id: %s name: %s alias: %s", agent.id, agent.name, agent.alias)

    def remove(self, agent: Agent):
        try:
            del self._agents[agent.id]
        except KeyError:
            logger.warning("Agent id: %s name: %s was not in dict by id", agent.id, agent.name)
        try:
            del self._agents_by_name[agent.name]
        except KeyError:
            logger.warning("Agent id: %s name: %s was not in dict by name", agent.id, agent.name)

    def all(self, reverse: bool = False) -> Generator[Agent, None, None]:
        for n in sorted(self._agents_by_name.keys(), key=lambda x: x.lower(), reverse=reverse):
            yield self._agents_by_name[n]


class HealthItem:
    """Represents single from->to connection health time-series entry"""

    def __init__(
        self,
        jitter_millisec: MetricValue,
        latency_millisec: MetricValue,
        packet_loss_percent: MetricValue,
        time: datetime,
    ) -> None:
        self.timestamp = time
        self.packet_loss_percent = Metric(type=MetricType.PACKET_LOSS, value=packet_loss_percent)

        # if packet loss is 100%, then jitter and latency measurements do not apply
        self.jitter_millisec = Metric(
            type=MetricType.JITTER,
            value=jitter_millisec if packet_loss_percent < MetricValue(100) else MetricValue("nan"),
        )
        self.latency_millisec = Metric(
            type=MetricType.LATENCY,
            value=latency_millisec if packet_loss_percent < MetricValue(100) else MetricValue("nan"),
        )

    def get_metric(self, metric_type: MetricType) -> Metric:
        if metric_type == MetricType.LATENCY:
            return self.latency_millisec
        if metric_type == MetricType.JITTER:
            return self.jitter_millisec
        if metric_type == MetricType.PACKET_LOSS:
            return self.packet_loss_percent
        raise Exception(f"MetricType not supported: {metric_type}")


@dataclass
class MeshColumn:
    """Represents connection "to" endpoint"""

    agent_id: AgentID = AgentID()
    health: List[HealthItem] = field(default_factory=list)  # sorted by timestamp from newest to oldest

    @property
    def latest_measurement(self) -> Optional[HealthItem]:
        """Latest connection health measurement, if available"""

        return self.health[0] if self.health else None

    def has_data(self) -> bool:
        """
        Determines if there are any observations available for this connection.
        Lack of observations may be caused by specifying incorrect time window in tests health request,
        or by the test itself being in paused state.
        """

        return len(self.health) > 0


class MeshRow:
    """Represents connection "from" endpoint"""

    def __init__(self, agent: Agent, columns: List[MeshColumn]):
        self.agent = agent
        self.columns = sorted(columns, key=lambda x: x.agent_id)

    @property
    def agent_id(self) -> AgentID:
        return self.agent.id


class ConnectionMatrix:
    """
    ConnectionMatrix holds "fromAgent" -> "toAgent" network connection metrics.
    It simplifies rendering test matrix table.
    Usage: matrix.connection("244", "532").latency_millisec
    """

    def __init__(self, rows: List[MeshRow]) -> None:
        connections: Dict[AgentID, Dict[AgentID, MeshColumn]] = {}
        for row in rows:
            connections[row.agent_id] = {}
            for col in row.columns:
                connections[row.agent_id][col.agent_id] = col
        self._connections = connections
        self.connection_timestamp_lowest, self.connection_timestamp_highest = self._get_lowest_highest_timestamp()

    def num_connections_with_health_data(self) -> int:
        count = 0
        for row in self._connections.values():
            for conn in row.values():
                if conn.has_data():
                    count += 1
        return count

    def incremental_update(self, src: ConnectionMatrix) -> None:
        """
        Update with src connections, add new connections if any, don't remove anything.
        Prerequisite: agents configuration hasn't change.
        """

        for from_agent_id in src._connections.keys():
            dst_row = self._connections.get(from_agent_id, {})  # get or create dst_row
            for to_agent_id, connection in src._connections[from_agent_id].items():
                # add or update connection
                if to_agent_id not in dst_row or connection.has_data():
                    dst_row[to_agent_id] = connection
            self._connections[from_agent_id] = dst_row

        self.connection_timestamp_lowest, self.connection_timestamp_highest = self._get_lowest_highest_timestamp()

    def connection(self, from_agent, to_agent: AgentID) -> MeshColumn:
        if from_agent not in self._connections:
            return MeshColumn()
        if to_agent not in self._connections[from_agent]:
            return MeshColumn()
        return self._connections[from_agent][to_agent]

    def _get_lowest_highest_timestamp(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        lowest: Optional[datetime] = None
        highest: Optional[datetime] = None

        for row in self._connections.values():
            for col in row.values():
                health = col.latest_measurement
                if not health:
                    continue
                if lowest is None or health.timestamp < lowest:
                    lowest = health.timestamp
                if highest is None or health.timestamp > highest:
                    highest = health.timestamp

        return lowest, highest


class MeshResults:
    """
    Internal representation of Mesh Test results; independent of source data structure like http
    or grpc synthetics client
    """

    def __init__(
        self, utc_last_updated: datetime, rows: Optional[List[MeshRow]] = None, agents: Agents = Agents()
    ) -> None:
        # The 'utc_last_updated' timestamp indicates time when data was fetched from the server,
        # as opposed to when it was actually collected. The latter is property of MeshColumn
        self.utc_last_updated = utc_last_updated
        self.agents = agents
        self.connection_matrix = ConnectionMatrix(rows if rows else [])
        # temporary fix working around inconsistent agent names returned by the API
        # 'mesh' rows in augmented test health response currently contain the most usable agent names
        # so update agents using this data while preserving other attributes retrieved with 'AgentsList'
        if rows:
            self._update_agents(rows)

    def _update_agents(self, rows: List[MeshRow]) -> None:
        """
        Update agent names and aliases based on row data while preserving other existing agent attributes
        NOTE: This is an ugly hack that should be removed as soon as Kentik API becomes little bit more consistent
        """
        for r in rows:
            agent = self.agents.get_by_id(r.agent.id)
            if agent.id == AgentID():
                agent = r.agent
                logging.warning("Agent %s (name: %s) was not in cache", agent.id, agent.name)
                self.agents.insert(agent)
            else:
                # We need to preserve other attributes retrieved from AgentsList, so we cannot simply replace the
                # existing agent. However, we need to delete it from the cache and re-insert it in order to
                # keep dictionary by name in sync
                self.agents.remove(agent)
                agent.name = r.agent.name
                agent.alias = r.agent.alias
                self.agents.insert(agent)

    def incremental_update(self, src: MeshResults) -> None:
        """Update with src data, add new pieces of data if any, don't remove anything"""

        if not self.can_incremental_update(src):
            raise Exception("Can't do incremental update - mesh test agents configuration mismatch")

        self.utc_last_updated = datetime.now(timezone.utc)
        self.connection_matrix.incremental_update(src.connection_matrix)

    def can_incremental_update(self, src: MeshResults) -> bool:
        return self.agents.equals(src.agents)

    def filter(self, from_agent, to_agent: AgentID, metric_type: MetricType) -> List[Tuple[datetime, MetricValue]]:
        items = self.connection(from_agent, to_agent).health
        return [(i.timestamp, i.get_metric(metric_type).value) for i in items]

    def connection(self, from_agent, to_agent: AgentID) -> MeshColumn:
        return self.connection_matrix.connection(from_agent, to_agent)

    @property
    def utc_timestamp_low(self) -> Optional[datetime]:
        """utc_timestamp_low can be None if there was no health data for specified time window (empty MeshResults)"""

        return self.connection_matrix.connection_timestamp_lowest

    @property
    def utc_timestamp_high(self) -> Optional[datetime]:
        """utc_timestamp_high can be None if there was no health data for specified time window (empty MeshResults)"""

        return self.connection_matrix.connection_timestamp_highest
