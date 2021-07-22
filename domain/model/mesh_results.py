from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from domain.geo import Coordinates
from domain.metric_type import MetricType
from domain.types import AgentID, MetricValue


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
class Metric:
    """Represents single from->to connection metric"""

    health: str = ""  # "healthy", "warning", ...
    value: MetricValue = MetricValue()


@dataclass
class HealthItem:
    """Represents single from->to connection health time-series entry"""

    jitter_millisec: MetricValue
    latency_millisec: MetricValue
    packet_loss_percent: MetricValue
    time: datetime


@dataclass
class MeshColumn:
    """Represents connection "to" endpoint"""

    agent_id: AgentID = AgentID()
    jitter_millisec: Metric = Metric()
    latency_millisec: Metric = Metric()
    packet_loss_percent: Metric = Metric()
    health: List[HealthItem] = field(default_factory=list)

    def has_no_data(self) -> bool:
        return self.packet_loss_percent.value == MetricValue(100) or len(self.health) == 0


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
        connections: Dict[AgentID, Dict[AgentID, MeshColumn]] = {}
        for row in rows:
            connections[row.agent_id] = {}
            for col in row.columns:
                connections[row.agent_id][col.agent_id] = col
        self._connections = connections

    def connection(self, from_agent, to_agent: AgentID) -> MeshColumn:
        if from_agent not in self._connections:
            return MeshColumn()
        if to_agent not in self._connections[from_agent]:
            return MeshColumn()
        return self._connections[from_agent][to_agent]


class MeshResults:
    """
    Internal representation of Mesh Test results; independent of source data structure like http
    or grpc synthetics client
    """

    def __init__(
        self,
        utc_timestamp: datetime,
        rows: Optional[List[MeshRow]] = None,
        agents: Agents = Agents(),
    ) -> None:
        self.utc_timestamp = utc_timestamp
        if rows is not None:
            self.rows = sorted(rows, key=lambda x: x.agent_id)
        else:
            self.rows = []
        self.agents = agents
        self._connection_matrix = ConnectionMatrix(self.rows)

    def filter(self, from_agent, to_agent: AgentID, metric: MetricType) -> List[Tuple[datetime, MetricValue]]:
        items = self.connection(from_agent, to_agent).health

        if metric == MetricType.LATENCY:
            return [(i.time, i.latency_millisec) for i in items]
        if metric == MetricType.JITTER:
            return [(i.time, i.jitter_millisec) for i in items]
        if metric == MetricType.PACKET_LOSS:
            return [(i.time, i.packet_loss_percent) for i in items]

        return []

    def connection(self, from_agent, to_agent: AgentID) -> MeshColumn:
        return self._connection_matrix.connection(from_agent, to_agent)
