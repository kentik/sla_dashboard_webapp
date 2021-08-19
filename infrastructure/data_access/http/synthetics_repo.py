import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from domain.metric import MetricValue
from domain.model import Agent, Agents, HealthItem, MeshColumn, MeshResults, MeshRow, Task, Tasks
from domain.model.mesh_results import Coordinates
from domain.types import AgentID, TaskID, TestID

# the below "disable=E0611" is needed as we don't commit the generated code into git repo and thus CI linter complains
# pylint: disable=E0611
from generated.synthetics_http_client.synthetics import ApiException
from generated.synthetics_http_client.synthetics.api.synthetics_data_service_api import (
    V202101beta1GetHealthForTestsRequest,
)
from generated.synthetics_http_client.synthetics.model.v202101beta1_mesh_column import V202101beta1MeshColumn
from generated.synthetics_http_client.synthetics.model.v202101beta1_mesh_metrics import V202101beta1MeshMetrics
from generated.synthetics_http_client.synthetics.model.v202101beta1_test_health import V202101beta1TestHealth

# pylint: enable=E0611
from infrastructure.data_access.http.api_client import KentikAPI

logger = logging.getLogger(__name__)


class SyntheticsRepo:
    """SyntheticsRepo implements domain.Repo protocol"""

    def __init__(
        self, email, token: str, synthetics_url: Optional[str] = None, timeout: Tuple[float, float] = (30.0, 30.0)
    ) -> None:
        if synthetics_url:
            self._api_client = KentikAPI(email=email, token=token, synthetics_url=synthetics_url)
        else:
            self._api_client = KentikAPI(email=email, token=token)
        self._timeout = timeout

    def get_mesh_test_results(
        self,
        test_id: TestID,
        agent_ids: List[AgentID],
        task_ids: List[TaskID],
        results_lookback_seconds: int,
        timeseries: bool,
    ) -> MeshResults:
        try:
            rows, tasks = self._get_rows_tasks(test_id, agent_ids, task_ids, results_lookback_seconds, timeseries)
            return MeshResults(
                utc_last_updated=datetime.now(timezone.utc), rows=rows, tasks=tasks, agents=self._get_agents(test_id)
            )
        except ApiException as err:
            raise Exception(f"Failed to fetch results for test ID: {test_id}") from err

    def _get_rows_tasks(
        self,
        test_id: TestID,
        agent_ids: List[AgentID],
        task_ids: List[TaskID],
        results_lookback_seconds: int,
        augment: bool,
    ) -> Tuple[List[MeshRow], Tasks]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(seconds=results_lookback_seconds)
        request = V202101beta1GetHealthForTestsRequest(
            ids=[test_id], agent_ids=agent_ids, task_ids=task_ids, start_time=start, end_time=end, augment=augment
        )

        response = self._api_client.synthetics_data_service.get_health_for_tests(
            request, _request_timeout=self._timeout
        )

        # response.health can be an empty list if no measurements were recorded in requested period of time
        # for example: right after mesh test was started, after mesh test was paused
        if len(response.health) == 0:
            return [], Tasks()

        most_recent_result = response.health[-1]
        return transform_to_internal_mesh_rows(most_recent_result), transform_to_internal_tasks(most_recent_result)

    def _get_agents(self, test_id) -> Agents:
        test_resp = self._api_client.synthetics_admin_service.test_get(test_id)
        agents_resp = self._api_client.synthetics_admin_service.agents_list()
        return make_internal_agents(agents_resp.agents, test_resp.test.settings.agent_ids)


def transform_to_internal_mesh_rows(data: V202101beta1TestHealth) -> List[MeshRow]:
    rows: List[MeshRow] = []
    for input_row in data.mesh:
        row = MeshRow(agent_id=AgentID(input_row.id), columns=transform_to_internal_mesh_columns(input_row.columns))
        rows.append(row)
    return rows


def transform_to_internal_mesh_columns(input_columns: List[V202101beta1MeshColumn]) -> List[MeshColumn]:
    columns = []
    for input_column in input_columns:
        column = MeshColumn(
            agent_id=AgentID(input_column.id), health=transform_to_internal_health_items(input_column.health)
        )
        columns.append(column)
    return columns


def transform_to_internal_health_items(input_health: List[V202101beta1MeshMetrics]) -> List[HealthItem]:
    health: List[HealthItem] = []
    for h in input_health:
        item = HealthItem(
            jitter_millisec=scale_us_to_ms(h.jitter.value),
            latency_millisec=scale_us_to_ms(h.latency.value),
            packet_loss_percent=scale_to_percents(h.packet_loss.value),
            time=h.time,
        )
        health.append(item)
    return health


def transform_to_internal_tasks(data: V202101beta1TestHealth) -> Tasks:
    tasks = Tasks()
    for task in data.tasks:
        tasks.insert(Task(id=task.task.id, target_ip=task.task.ping.target, period_seconds=task.task.ping.period))
    return tasks


def scale_us_to_ms(val: str) -> MetricValue:
    return MetricValue(float(val) / 1000.0)


def scale_to_percents(val: str) -> MetricValue:
    # scale 0..1 -> 0..100
    return MetricValue(float(val) * 100.0)


def make_internal_agents(agents, agent_ids) -> Agents:
    result = Agents()
    for agent in agents:
        if agent.id in agent_ids:
            result.insert(
                Agent(
                    id=AgentID(agent.id),
                    ip=agent.ip,
                    name=agent.name,
                    alias=agent.alias,
                    coords=Coordinates(agent.long, agent.lat),
                )
            )
    return result
