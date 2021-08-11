from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from domain.geo import Coordinates
from domain.metric_type import MetricType
from domain.types import AgentID, MetricValue

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

    def equals(self, other: Agents) -> bool:
        return self._agents == other._agents

    def get_by_id(self, agent_id: AgentID) -> Agent:
        if agent_id in self._agents:
            return self._agents[agent_id]
        return Agent()

    def get_by_alias(self, alias: str) -> Agent:
        for _, v in self._agents.items():
            if v.alias == alias:
                return v
        return Agent()

    def get_alias(self, agent_id: AgentID) -> str:
        agent = self.get_by_id(agent_id)
        if agent.id == AgentID():
            return f"[agent_id={agent_id} not found]"
        return agent.alias

    def insert(self, agent: Agent) -> None:
        self._agents[agent.id] = agent


@dataclass
class HealthItem:
    """Represents single from->to connection health time-series entry"""

    jitter_millisec: MetricValue
    latency_millisec: MetricValue
    packet_loss_percent: MetricValue
    timestamp: datetime


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
        Lack of observations may be caused by specyfing incorrect time window in tests health request,
        or by the test itself being in paused state.
        """

        return len(self.health) > 0

    def is_live(self) -> bool:
        """Determines if there actually is a connection and the packets reach the destination"""

        health = self.latest_measurement
        return health is not None and health.packet_loss_percent < MetricValue(100.0)


class MeshRow:
    """Represents connection "from" endpoint"""

    def __init__(self, agent_id: AgentID, columns: List[MeshColumn]):
        self.agent_id = agent_id
        self.columns = sorted(columns, key=lambda x: x.agent_id)


class ConnectionMatrix:
    """
    ConnectionMatrix holds "fromAgent" -> "toAgent" network connection metrics.
    It simplifies rendering test matrix table.
    Usage: matrix.connection("244", "532").latency_millisec
    """

    def __init__(self, rows: List[MeshRow]) -> None:
        agent_ids: List[AgentID] = []
        connections: Dict[AgentID, Dict[AgentID, MeshColumn]] = {}
        for row in rows:
            agent_ids.append(row.agent_id)
            connections[row.agent_id] = {}
            for col in row.columns:
                connections[row.agent_id][col.agent_id] = col
        self._connections = connections
        self.agent_ids = sorted(agent_ids)
        self.connection_timestamp_lowest, self.connection_timestamp_highest = self._get_lowest_highest_timestamp()

    def incremental_update(self, src: ConnectionMatrix) -> None:
        """
        Update with src connections, add new connections if any, don't remove anything.
        Prerequisite: agents configuration hasn't change.
        """

        for from_agent_id in src._connections.keys():
            dst_row = self._connections[from_agent_id]  # get or insert
            for to_agent_id, connection in src._connections[from_agent_id].items():
                # add or update connection
                if to_agent_id not in dst_row or connection.has_data():
                    dst_row[to_agent_id] = connection
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

        # utc_last_updated is when the data was fetched from the server, as opposed to when the data was actually collected.
        # the latter is a property of MeshColumn
        self.utc_last_updated = utc_last_updated
        self.agents = agents
        self.connection_matrix = ConnectionMatrix(rows if rows else [])

    def incremental_update(self, src: MeshResults) -> None:
        """Update with src data, add new pieces of data if any, don't remove anything"""

        if not self.agents.equals(src.agents):
            logger.warning("Mesh test agents configuration mismatch. Skipping incremental update")
            return

        self.utc_last_updated = datetime.now(timezone.utc)
        self.connection_matrix.incremental_update(src.connection_matrix)

    def filter(self, from_agent, to_agent: AgentID, metric: MetricType) -> List[Tuple[datetime, MetricValue]]:
        items = self.connection(from_agent, to_agent).health

        if metric == MetricType.LATENCY:
            return [(i.timestamp, i.latency_millisec) for i in items]
        if metric == MetricType.JITTER:
            return [(i.timestamp, i.jitter_millisec) for i in items]
        if metric == MetricType.PACKET_LOSS:
            return [(i.timestamp, i.packet_loss_percent) for i in items]

        return []

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
