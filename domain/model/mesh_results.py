from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from domain.metric import Metric, MetricType, MetricValue
from domain.model.agents import Agent, Agents
from domain.types import IP, AgentID, TaskID

logger = logging.getLogger(__name__)


@dataclass
class Task:
    id: TaskID
    target_ip: IP
    period_seconds: int


class Tasks:
    def __init__(self) -> None:
        self._tasks: Dict[IP, Task] = {}

    def insert(self, task: Task) -> None:
        self._tasks[task.target_ip] = task

    def get_by_ip(self, target_ip: IP) -> Optional[Task]:
        return self._tasks.get(target_ip)

    def incremental_update(self, src: Tasks) -> None:
        """Update with new tasks, don't remove anything"""

        self._tasks.update(src._tasks)


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


class MeshColumn:
    """Represents connection "to" endpoint"""

    def __init__(self, agent_id: AgentID = AgentID(), health: Optional[List[HealthItem]] = None) -> None:
        # sort by timestamp from newest to oldest
        self.health = sorted(health, key=lambda item: item.timestamp, reverse=True) if health else []
        self.agent_id = agent_id

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
        self.connection_timestamp_oldest, self.connection_timestamp_newest = self._get_timestamp_range()

    def incremental_update(self, src: ConnectionMatrix) -> None:
        """
        Update with src connections, add new connections if any, don't remove anything.
        """

        for from_agent_id in src._connections.keys():
            dst_row = self._connections.get(from_agent_id, {})  # get or create dst_row
            for to_agent_id, update_conn in src._connections[from_agent_id].items():
                cached_conn = dst_row.get(to_agent_id)
                dst_row[to_agent_id] = self._update(cached_conn, update_conn)
            self._connections[from_agent_id] = dst_row
        self.connection_timestamp_oldest, self.connection_timestamp_newest = self._get_timestamp_range()

    def drop_samples_older_than(self, threshold: datetime) -> None:
        for row in self._connections.values():
            for conn in row.values():
                n = 0
                while conn.health and conn.health[-1].timestamp < threshold:
                    conn.health.pop()
                    n += 1
                if n > 0:
                    logger.debug("Dropped %d samples older than %s", n, threshold.isoformat())
        self.connection_timestamp_oldest, self.connection_timestamp_newest = self._get_timestamp_range()

    def num_connections_with_data(self) -> int:
        count = 0
        for row in self._connections.values():
            for conn in row.values():
                if conn.has_data():
                    count += 1
        return count

    def connection(self, from_agent, to_agent: AgentID) -> MeshColumn:
        if from_agent not in self._connections:
            return MeshColumn()
        if to_agent not in self._connections[from_agent]:
            return MeshColumn()
        return self._connections[from_agent][to_agent]

    def _get_timestamp_range(self) -> Tuple[Optional[datetime], Optional[datetime]]:
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

    @staticmethod
    def _update(cached_conn: Optional[MeshColumn], update_conn: MeshColumn) -> MeshColumn:
        """Update cache if update is newer or just as fresh but has more timeseries data"""

        # 1. no such connection in cache yet - replace with whatever comes
        if not cached_conn:
            return update_conn

        # 2. connection in cache but has no timeseries data at all - replace
        cached_latest = cached_conn.latest_measurement
        if not cached_latest:
            return update_conn

        # 3. connection in cache, has timeseries data, and update brings no timeseries data - keep cache
        update_latest = update_conn.latest_measurement
        if not update_latest:
            return cached_conn

        # 4. cached connection is older than update connection
        if cached_latest.timestamp < update_latest.timestamp:
            # accumulate historical timeseries data
            update_oldest_timestamp = update_conn.health[-1].timestamp
            cached_items_to_keep = [h for h in cached_conn.health if h.timestamp < update_oldest_timestamp]
            combined = update_conn
            combined.health += cached_items_to_keep
            return combined

        # 5. cached connection is newer than update. Should never happen
        if cached_latest.timestamp > update_latest.timestamp:
            logger.debug(
                "Cached connection is newer than update connection: %s vs %s",
                cached_latest.timestamp,
                update_latest.timestamp,
            )
            return cached_conn

        # 6. cached and update are equally fresh but update brings more data
        if len(update_conn.health) > len(cached_conn.health):
            return update_conn

        return cached_conn


class MeshResults:
    """
    Internal representation of Mesh Test results; independent of source data structure like http
    or grpc synthetics client
    """

    def __init__(
        self,
        rows: Optional[List[MeshRow]] = None,
        tasks: Tasks = Tasks(),
    ) -> None:
        self.tasks = tasks
        rows = rows or []
        self.participating_agents = Agents()
        for r in rows:
            self.participating_agents.insert(r.agent)
        self.connection_matrix = ConnectionMatrix(rows)

    def incremental_update(self, src: MeshResults) -> None:
        """Update with src data, add new pieces of data if any, don't remove anything"""

        self.tasks.incremental_update(src.tasks)
        self.connection_matrix.incremental_update(src.connection_matrix)
        self.participating_agents = src.participating_agents

    def filter(self, from_agent, to_agent: AgentID, metric_type: MetricType) -> List[Tuple[datetime, MetricValue]]:
        items = self.connection(from_agent, to_agent).health
        return [(i.timestamp, i.get_metric(metric_type).value) for i in items]

    def connection(self, from_agent, to_agent: AgentID) -> MeshColumn:
        return self.connection_matrix.connection(from_agent, to_agent)

    @property
    def utc_timestamp_oldest(self) -> Optional[datetime]:
        """utc_timestamp_oldest can be None if there was no health data for specified time window (empty MeshResults)"""

        return self.connection_matrix.connection_timestamp_oldest

    @property
    def utc_timestamp_newest(self) -> Optional[datetime]:
        """utc_timestamp_newest can be None if there was no health data for specified time window (empty MeshResults)"""

        return self.connection_matrix.connection_timestamp_newest
