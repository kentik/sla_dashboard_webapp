from dataclasses import dataclass, field
from datetime import datetime, timezone
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

    def get_by_id(self, id: AgentID) -> Agent:
        if id in self._agents:
            return self._agents[id]
        return Agent()

    def get_by_alias(self, alias: str) -> Agent:
        for _, v in self._agents.items():
            if v.alias == alias:
                return v
        return Agent()

    def get_alias(self, id: AgentID) -> str:
        agent = self.get_by_id(id)
        if agent.id == AgentID():
            return f"[agent_id={id} not found]"
        return agent.alias

    def insert(self, agent: Agent) -> None:
        self._agents[agent.id] = agent


@dataclass
class Metric:
    """ Represents single from->to connection metric """

    health: str = ""  # "healthy", "warning", ...
    value: MetricValue = MetricValue()


@dataclass
class HealthItem:
    """ Represents single from->to connection health timeseries entry """

    jitter_millisec: MetricValue
    latency_millisec: MetricValue
    packet_loss_percent: MetricValue
    time: datetime


@dataclass
class MeshColumn:
    """ Represents connection "to" endpoint """

    agent_id: AgentID = AgentID()
    jitter_millisec: Metric = Metric()
    latency_millisec: Metric = Metric()
    packet_loss_percent: Metric = Metric()
    health: List[HealthItem] = field(default_factory=list)

    def is_no_data(self) -> bool:
        return self.packet_loss_percent.value == MetricValue(100) or self.health == []


@dataclass
class MeshRow:
    """ Represents connection "from" endpoint """

    agent_id: AgentID
    columns: List[MeshColumn]


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
    """Internal representation of Mesh Test results; independent of source data structure like http or grpc synthetics client"""

    def __init__(
        self,
        utc_timestamp: Optional[datetime] = None,
        rows: List[MeshRow] = [],
        agents: Agents = Agents(),
    ) -> None:
        if utc_timestamp is None:
            utc_timestamp = datetime.now(timezone.utc)

        self.utc_timestamp = utc_timestamp
        self.rows = rows
        self.agents = agents
        self._connection_matrix = ConnectionMatrix(rows)

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
