import itertools
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import dash_core_components as dcc
import dash_html_components as html

from domain.config import Config, MatrixCellColor
from domain.config.thresholds import Thresholds
from domain.geo import calc_distance
from domain.metric_type import MetricType
from domain.model import MeshResults
from domain.model.mesh_results import Agents, MeshColumn
from domain.types import AgentID, MetricValue, Threshold


# SLALevel represents measured value in regard to threshold, as a value in connection matrix cell
class SLALevel(float, Enum):
    HEALTHY = 0.0
    WARNING = 0.5
    CRITICAL = 1.0


# SLALevelColumn represents SLALevel single column in connectin matrix
SLALevelColumn = List[Optional[SLALevel]]


class MatrixView:
    MATRIX = "matrix"
    METRIC_SELECTOR = "metric-selector"

    def __init__(self, config: Config) -> None:
        self._config = config
        self._agents = Agents()

    def make_layout(self, mesh: MeshResults, metric: MetricType, config: Config) -> html.Div:
        self._agents = mesh.agents  # remember agents used to make the layout for further processing
        timestampISO = mesh.utc_timestamp.isoformat()
        header = "SLA Dashboard"
        fig = self.make_figure(mesh, metric)
        return html.Div(
            children=[
                html.H1(children=header, className="header_main"),
                html.Div(
                    children=[
                        html.H2(
                            children=[
                                html.Span("Data timestamp"),
                                html.Span(
                                    "<test_results_date_time>",
                                    className="header-timestamp",
                                    id="current-timestamp",
                                    title=timestampISO,
                                ),
                                html.Span(
                                    self._config.data_update_period_seconds,
                                    className="header-time-interval",
                                    id="timeinterval",
                                ),
                            ],
                            className="header__subTitle",
                        ),
                        html.Div("warning: data is stale", className="header-stale-data-warning"),
                        html.Div(
                            children=[
                                html.Label("Select primary metric:", className="select_label"),
                                dcc.Dropdown(
                                    id=self.METRIC_SELECTOR,
                                    options=[
                                        {"label": "Latency [ms]", "value": MetricType.LATENCY.value},
                                        {"label": "Jitter [ms]", "value": MetricType.JITTER.value},
                                        {"label": "Packet loss [%]", "value": MetricType.PACKET_LOSS.value},
                                    ],
                                    value=metric.value,
                                    clearable=False,
                                    className="dropdowns",
                                ),
                            ],
                            className="select_container",
                        ),
                        html.Div(
                            children=[
                                html.Div(
                                    dcc.Graph(id=self.MATRIX, style={"width": 900, "height": 750}, figure=fig),
                                    className="chart__default",
                                ),
                                html.Div(
                                    children=[
                                        html.Label(
                                            "Healthy", className="chart_legend__label chart_legend__label_healthy"
                                        ),
                                        html.Div(
                                            className="chart_legend__cell",
                                            style={"background": self._config.matrix.cell_color_healthy},
                                        ),
                                        html.Label(
                                            "Warning", className="chart_legend__label chart_legend__label_warning"
                                        ),
                                        html.Div(
                                            className="chart_legend__cell",
                                            style={"background": self._config.matrix.cell_color_warning},
                                        ),
                                        html.Label(
                                            "Critical", className="chart_legend__label chart_legend__label_critical"
                                        ),
                                        html.Div(
                                            className="chart_legend__cell",
                                            style={"background": self._config.matrix.cell_color_critical},
                                        ),
                                    ],
                                    className="chart_legend",
                                ),
                            ],
                            className="chart_container",
                        ),
                    ],
                    className="main_container",
                ),
            ],
        )

    def make_figure(self, mesh: MeshResults, metric: MetricType) -> Dict:
        data = self.make_figure_data(mesh, metric)
        annotations = self.make_figure_annotations(mesh, metric)
        layout = dict(
            margin=dict(l=150, b=50, t=100, r=50),
            modebar={"orientation": "v"},
            annotations=annotations,
            xaxis=dict(side="top", ticks="", scaleanchor="y"),
            yaxis=dict(side="left", ticks=""),
            hovermode="closest",
            showlegend=False,
        )

        return {"data": [data], "layout": layout}

    def make_figure_data(self, mesh: MeshResults, metric: MetricType) -> Dict:
        labels = [mesh.agents.get_by_id(row.agent_id).alias for row in mesh.rows]
        reversed_labels = list(reversed(labels))
        sla_levels = self.make_sla_levels(mesh, metric)
        return dict(
            x=labels,
            y=reversed_labels,
            z=sla_levels,
            text=self.make_hover_text(mesh),
            type="heatmap",
            hoverinfo="text",
            opacity=1,
            name="",
            showscale=False,
            colorscale=self.make_color_scale(sla_levels),
        )

    def make_sla_levels(self, mesh: MeshResults, metric: MetricType) -> List[SLALevelColumn]:
        thresholds = self.get_thresholds(metric)
        sla_levels: List[SLALevelColumn] = []

        for row in reversed(mesh.rows):
            sla_levels_col: SLALevelColumn = []
            for col in row.columns:
                warning = thresholds.warning(row.agent_id, col.agent_id)
                critical = thresholds.critical(row.agent_id, col.agent_id)
                value = self.get_metric_value(metric, mesh.connection(row.agent_id, col.agent_id))
                sla_level = self.get_sla_level(value, warning, critical)
                sla_levels_col.append(sla_level)
            sla_levels.append(sla_levels_col)

        for i in range(len(mesh.rows)):  # add Nones at diagonal to avoid colorising it
            sla_levels[-(i + 1)].insert(i, None)

        return sla_levels

    def get_thresholds(self, metric: MetricType) -> Thresholds:
        if metric == MetricType.LATENCY:
            return self._config.latency
        if metric == MetricType.JITTER:
            return self._config.jitter
        return self._config.packet_loss

    @staticmethod
    def get_metric_value(metric: MetricType, cell: MeshColumn) -> MetricValue:
        if metric == MetricType.LATENCY:
            return cell.latency_millisec.value
        if metric == MetricType.JITTER:
            return cell.jitter_millisec.value
        return cell.packet_loss_percent.value

    @classmethod
    def make_figure_annotations(cls, mesh: MeshResults, metric: MetricType) -> List[Dict]:
        annotations: List[Dict] = []
        for row in reversed(mesh.rows):
            for col in row.columns:
                from_agent = mesh.agents.get_by_id(row.agent_id)
                to_agent = mesh.agents.get_by_id(col.agent_id)
                text = cls.get_text(metric, mesh.connection(from_agent.id, to_agent.id))
                annotations.append(
                    dict(
                        showarrow=False,
                        text=text,
                        xref="x",
                        yref="y",
                        x=to_agent.alias,
                        y=from_agent.alias,
                    )
                )
        return annotations

    @staticmethod
    def get_text(metric: MetricType, cell: MeshColumn) -> str:
        if metric == MetricType.LATENCY:
            return f"<b>{(cell.latency_millisec.value):.2f} ms</b>"
        if metric == MetricType.JITTER:
            return f"<b>{(cell.jitter_millisec.value):.2f} ms</b>"
        return f"<b>{cell.packet_loss_percent.value:.1f}%</b>"

    def make_hover_text(self, mesh: MeshResults) -> List[List[str]]:
        text = []
        for row in reversed(mesh.rows):
            text_col = []
            for col in row.columns:
                from_agent = mesh.agents.get_by_id(row.agent_id)
                to_agent = mesh.agents.get_by_id(col.agent_id)
                conn = mesh.connection(from_agent.id, to_agent.id)
                latency_ms = conn.latency_millisec.value
                jitter_ms = conn.jitter_millisec.value
                loss = conn.packet_loss_percent.value
                distance_unit = self._config.distance_unit
                distance = calc_distance(from_agent.coords, to_agent.coords, distance_unit)
                text_col.append(
                    f"{from_agent.alias} -> {to_agent.alias} <br>"
                    + f"Distance: {distance:.0f} {distance_unit.value}<br>"
                    + f"Latency: {latency_ms:.2f} ms <br>"
                    + f"Jitter: {jitter_ms:.2f} ms <br>"
                    + f"Loss: {loss:.1f}%"
                )
            text.append(text_col)
        for i in range(len(mesh.rows)):
            text[-(i + 1)].insert(i, "")

        return text

    @staticmethod
    def get_sla_level(val: MetricValue, warning_threshold: Threshold, critical_threshold: Threshold) -> SLALevel:
        if val < warning_threshold:
            return SLALevel.HEALTHY
        if val < critical_threshold:
            return SLALevel.WARNING
        return SLALevel.CRITICAL

    def make_color_scale(self, z: List[SLALevelColumn]) -> List[Tuple[SLALevel, MatrixCellColor]]:
        healthy = self._config.matrix.cell_color_healthy
        warning = self._config.matrix.cell_color_warning
        critical = self._config.matrix.cell_color_critical

        if all([val is None or val == SLALevel.HEALTHY for val in itertools.chain(*z)]):
            return [(SLALevel.HEALTHY, healthy), (SLALevel.CRITICAL, healthy)]
        if all([val is None or val == SLALevel.WARNING for val in itertools.chain(*z)]):
            return [(SLALevel.HEALTHY, warning), (SLALevel.CRITICAL, warning)]
        if all([val is None or val == SLALevel.CRITICAL for val in itertools.chain(*z)]):
            return [(SLALevel.HEALTHY, critical), (SLALevel.CRITICAL, critical)]
        if not any([val == SLALevel.HEALTHY for val in itertools.chain(*z)]):
            return [(SLALevel.HEALTHY, warning), (SLALevel.CRITICAL, critical)]
        if not any([val == SLALevel.CRITICAL for val in itertools.chain(*z)]):
            return [(SLALevel.HEALTHY, healthy), (SLALevel.CRITICAL, warning)]
        return [(SLALevel.HEALTHY, healthy), (SLALevel.WARNING, warning), (SLALevel.CRITICAL, critical)]

    def get_agents_from_click(self, clickData: Optional[Dict[str, Any]]) -> Tuple[Optional[AgentID], Optional[AgentID]]:
        if clickData is None:
            return None, None

        to_agent_alias, from_agent_alias = clickData["points"][0]["x"], clickData["points"][0]["y"]
        return self._agents.get_by_alias(from_agent_alias).id, self._agents.get_by_alias(to_agent_alias).id
