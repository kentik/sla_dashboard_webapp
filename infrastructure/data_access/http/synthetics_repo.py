from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from domain.model import Agent, Agents, HealthItem, MeshColumn, MeshResults, MeshRow, Metric
from domain.model.mesh_results import Coordinates
from domain.types import AgentID, MetricValue, TestID

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


class SyntheticsRepo:
    """SyntheticsRepo implements domain.Repo protocol"""

    def __init__(self, email, token: str, timeout: Tuple[float, float] = (30.0, 30.0)) -> None:
        self._api_client = KentikAPI(email=email, token=token)
        self._timeout = timeout

    def get_mesh_test_results(self, test_id: TestID, results_lookback_seconds: int) -> MeshResults:
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(seconds=results_lookback_seconds)

            request = V202101beta1GetHealthForTestsRequest(ids=[test_id], start_time=start, end_time=end, augment=True)
            response = self._api_client.synthetics.get_health_for_tests(request, _request_timeout=self._timeout)

            if len(response.health) == 0:
                raise Exception("get_health_for_tests returned 0 items")

            most_recent_result = response.health[-1]
            rows = transform_to_internal_mesh_rows(most_recent_result)
            agents = transform_to_internal_agents(most_recent_result)
            return MeshResults(datetime.now(timezone.utc), rows, agents)
        except ApiException as err:
            raise Exception(f"Failed to fetch results for test id: {test_id}") from err


def transform_to_internal_agents(data: V202101beta1TestHealth) -> Agents:
    agents = Agents()
    for task in data.tasks:
        for agentHealth in task.agents:
            input_agent = agentHealth.agent
            agent = Agent(
                id=AgentID(input_agent.id),
                ip=input_agent.ip,
                name=input_agent.name,
                alias=input_agent.alias,
                coords=Coordinates(input_agent.long, input_agent.lat),
            )
            agents.insert(agent)
    return agents


def transform_to_internal_mesh_rows(data: V202101beta1TestHealth) -> List[MeshRow]:
    rows: List[MeshRow] = []
    for input_row in data.mesh:
        row = MeshRow(
            agent_id=AgentID(input_row.id),
            columns=transform_to_internal_mesh_columns(input_row.columns),
        )
        rows.append(row)
    return rows


def transform_to_internal_mesh_columns(input_columns: List[V202101beta1MeshColumn]) -> List[MeshColumn]:
    columns = []
    for input_column in input_columns:
        column = MeshColumn(
            agent_id=AgentID(input_column.id),
            jitter_millisec=Metric(
                health=input_column.metrics.jitter.health,
                value=scale_us_to_ms(input_column.metrics.jitter.value),
            ),
            latency_millisec=Metric(
                health=input_column.metrics.latency.health,
                value=scale_us_to_ms(input_column.metrics.latency.value),
            ),
            packet_loss_percent=Metric(
                health=input_column.metrics.packet_loss.health,
                value=scale_to_percents(input_column.metrics.packet_loss.value),
            ),
            health=transform_to_internal_health_items(input_column.health),
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


def scale_us_to_ms(val: str) -> MetricValue:
    return MetricValue(float(val) / 1000.0)


def scale_to_percents(val: str) -> MetricValue:
    # scale 0..1 -> 0..100
    return MetricValue(float(val) * 100.0)
