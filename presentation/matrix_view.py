import logging
import math
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import dash_core_components as dcc
import dash_html_components as html

from domain.config import Config, MatrixCellColor
from domain.config.thresholds import Thresholds
from domain.geo import calc_distance
from domain.metric import MetricType, MetricValue
from domain.model import MeshResults
from domain.model.mesh_results import Agent, Agents, HealthItem
from domain.types import AgentID, Threshold

# Connections are displayed as a matrix using dcc.Graph component.
# The Graph is configured as a heatmap.
# In heatmap, each cell is assigned a floating-point type value.
# The heatmap itself is assigned a color scale that maps range [0.0 - 1.0] to colors.
# The heatmap dynamically "stretches" it's color scale range to cover all cells values.
# We make sure to always have values in range [0.0 - 1.0] in our matrix,
# so that no range stretching occurs and coloring works as expected.


# SLALevel maps connection state to a value in connection matrix, in range [0.0 - 1.0]
class SLALevel(float, Enum):
    _MIN = 0.0
    HEALTHY = 0.2
    WARNING = 0.4
    CRITICAL = 0.6
    NODATA = 0.8
    _MAX = 1.0


# SLALevelColumn represents SLALevel single column in connection matrix
SLALevelColumn = List[Optional[SLALevel]]


def agent_label(agent: Agent) -> str:
    return agent.name


class MatrixView:
    MATRIX = "matrix"
    METRIC_SELECTOR = "metric-selector"

    def __init__(self, config: Config) -> None:
        self._config = config
        self._agents = Agents()
        self._color_scale = self._make_color_scale()

    def make_layout(self, mesh: MeshResults, metric: MetricType) -> html.Div:
        title = "SLA Dashboard"
        if mesh.connection_matrix.num_connections_with_health_data() > 0:
            content = self.make_matrix_content(mesh, metric)
        else:
            content = self.make_no_data_content()

        return html.Div(
            children=[
                html.H1(children=title, className="header_main"),
                html.Div(children=content, className="main_container"),
            ]
        )

    def make_matrix_content(self, mesh: MeshResults, metric: MetricType) -> List:
        self._agents = mesh.agents  # remember agents used to make the layout for further processing
        timestamp_low_iso = mesh.utc_timestamp_low.isoformat() if mesh.utc_timestamp_low else None
        timestamp_high_iso = mesh.utc_timestamp_high.isoformat() if mesh.utc_timestamp_high else None
        fig = self.make_figure(mesh, metric)

        return [
            html.H2(
                children=[
                    html.Span("Data timestamp range: "),
                    html.Span(
                        "<test_results_timestamp_low>",
                        className="header-timestamp",
                        id="timestamp-low",
                        title=timestamp_low_iso,
                    ),
                    html.Span(" - ", className="header-timestamp"),
                    html.Span(
                        "<test_results_timestamp_high>",
                        className="header-timestamp",
                        id="timestamp-high",
                        title=timestamp_high_iso,
                    ),
                ],
                className="header__subTitle",
            ),
            html.Div(
                children=[
                    html.Label("Select primary metric:", className="select_label"),
                    dcc.Dropdown(
                        id=self.METRIC_SELECTOR,
                        options=[{"label": f"{m.value} [{m.unit}]", "value": m.value} for m in MetricType],
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
                        dcc.Graph(id=self.MATRIX, figure=fig, responsive=True),
                        className="chart__default",
                    ),
                    html.Div(
                        children=[
                            html.Label("Healthy", className="chart_legend__label chart_legend__label_healthy"),
                            html.Div(
                                className="chart_legend__cell",
                                style={"background": self._config.matrix.cell_color_healthy},
                            ),
                            html.Label("Warning", className="chart_legend__label chart_legend__label_warning"),
                            html.Div(
                                className="chart_legend__cell",
                                style={"background": self._config.matrix.cell_color_warning},
                            ),
                            html.Label("Critical", className="chart_legend__label chart_legend__label_critical"),
                            html.Div(
                                className="chart_legend__cell",
                                style={"background": self._config.matrix.cell_color_critical},
                            ),
                            html.Label("No data", className="chart_legend__label chart_legend__label_nodata"),
                            html.Div(
                                className="chart_legend__cell",
                                style={"background": self._config.matrix.cell_color_nodata},
                            ),
                        ],
                        className="chart_legend",
                    ),
                ],
                className="chart_container",
            ),
        ]

    def make_no_data_content(self) -> List:
        no_data = f"No test results available for the last {int(self._config.data_update_lookback_seconds/60)} minutes"
        return [html.H1(no_data), html.Br(), html.Br()]

    def make_figure(self, mesh: MeshResults, metric: MetricType) -> Dict:
        data = self.make_figure_data(mesh, metric)
        annotations = self.make_figure_annotations(mesh, metric)
        layout = dict(
            margin=dict(l=200, b=0, t=100, r=0),
            modebar={"orientation": "v"},
            annotations=annotations,
            xaxis=dict(side="top", ticks="", scaleanchor="y"),
            yaxis=dict(side="left", ticks=""),
            hovermode="closest",
            showlegend=False,
            autosize=True,
        )
        return {"data": [data], "layout": layout}

    def make_figure_data(self, mesh: MeshResults, metric: MetricType) -> Dict:
        x_labels = [agent_label(agent) for agent in mesh.agents.all()]
        y_labels = list(reversed(x_labels))
        sla_levels = self.make_sla_levels(mesh, metric)
        return dict(
            x=x_labels,
            y=y_labels,
            z=sla_levels,
            text=self.make_matrix_hover_text(mesh),
            type="heatmap",
            hoverinfo="text",
            opacity=1,
            name="",
            showscale=False,
            autosize=True,
            colorscale=self._color_scale,
        )

    def make_sla_levels(self, mesh: MeshResults, metric_type: MetricType) -> List[SLALevelColumn]:
        thresholds = self.get_thresholds(metric_type)
        sla_levels: List[SLALevelColumn] = []

        for from_agent in mesh.agents.all(reverse=True):
            sla_levels_col: SLALevelColumn = []
            for i, to_agent in enumerate(mesh.agents.all()):
                if from_agent == to_agent:
                    sla_level = SLALevel(i % 2)
                else:
                    warning = thresholds.warning(from_agent.id, to_agent.id)
                    critical = thresholds.critical(from_agent.id, to_agent.id)
                    health = mesh.connection(from_agent.id, to_agent.id).latest_measurement
                    if health:
                        metric = health.get_metric(metric_type)
                        sla_level = self.get_sla_level(metric.value, warning, critical)
                    else:
                        sla_level = SLALevel.NODATA
                sla_levels_col.append(sla_level)
            sla_levels.append(sla_levels_col)

        return sla_levels

    def get_thresholds(self, metric: MetricType) -> Thresholds:
        if metric == MetricType.LATENCY:
            return self._config.latency
        if metric == MetricType.JITTER:
            return self._config.jitter
        return self._config.packet_loss

    @classmethod
    def make_figure_annotations(cls, mesh: MeshResults, metric: MetricType) -> List[Dict]:
        annotations: List[Dict] = []
        for from_agent in mesh.agents.all(reverse=True):
            for to_agent in mesh.agents.all():
                if from_agent == to_agent:
                    text = ""
                else:
                    health = mesh.connection(from_agent.id, to_agent.id).latest_measurement
                    text = cls.format_health(metric, health, False, "")
                annotations.append(
                    dict(
                        showarrow=False,
                        text=text,
                        xref="x",
                        yref="y",
                        x=agent_label(to_agent),
                        y=agent_label(from_agent),
                    )
                )
        return annotations

    @staticmethod
    def format_health(
        metric_type: MetricType, health: Optional[HealthItem], include_unit: bool = False, nan="N/A"
    ) -> str:
        if not health:
            return nan

        metric = health.get_metric(metric_type)
        if math.isnan(metric.value):
            return nan

        return "{:.2f}{}".format(metric.value, metric.unit if include_unit else "")

    def make_matrix_hover_text(self, mesh: MeshResults) -> List[List[str]]:
        # make hover text for each cell in the matrix
        matrix_hover_text: List[List[str]] = []
        for from_agent in mesh.agents.all(reverse=True):
            column_hover_text: List[str] = []
            for to_agent in mesh.agents.all():
                column_hover_text.append(self.make_cell_hover_text(from_agent, to_agent, mesh))
            matrix_hover_text.append(column_hover_text)

        return matrix_hover_text

    def make_cell_hover_text(self, from_agent: Agent, to_agent: Agent, mesh: MeshResults) -> str:
        if from_agent == to_agent:
            return ""
        conn = mesh.connection(from_agent.id, to_agent.id)
        distance_unit = self._config.distance_unit
        distance = calc_distance(from_agent.coords, to_agent.coords, distance_unit)

        cell_hover_text: List[str] = [
            f"From: {from_agent.name}, {from_agent.alias} [{from_agent.id}]",
            f"To: {to_agent.name}, {to_agent.alias} [{to_agent.id}]",
            f"Distance: {distance:.0f} {distance_unit.value}",
        ]

        health = conn.latest_measurement
        if health:
            for m in MetricType:
                cell_hover_text.append(f"{m.value}: {self.format_health(m, health, True)}")
            cell_hover_text.append(f"Time stamp: {health.timestamp.strftime('%x %X %Z')}")
        else:
            # no data available for this connection
            cell_hover_text.append("NO DATA")

        return "<br>".join(cell_hover_text)

    @staticmethod
    def get_sla_level(val: MetricValue, warning_threshold: Threshold, critical_threshold: Threshold) -> SLALevel:
        if math.isnan(val):
            return SLALevel.NODATA
        if val < warning_threshold:
            return SLALevel.HEALTHY
        if val < critical_threshold:
            return SLALevel.WARNING
        return SLALevel.CRITICAL

    # noinspection PyProtectedMember
    def _make_color_scale(self) -> List[Tuple[SLALevel, MatrixCellColor]]:
        healthy = self._config.matrix.cell_color_healthy
        warning = self._config.matrix.cell_color_warning
        critical = self._config.matrix.cell_color_critical
        no_data = self._config.matrix.cell_color_nodata
        diagonal = "rgba(0, 0, 0, 0.0)"  # diagonal is transparent

        return [
            (SLALevel._MIN, diagonal),
            (SLALevel.HEALTHY, healthy),
            (SLALevel.WARNING, warning),
            (SLALevel.CRITICAL, critical),
            (SLALevel.NODATA, no_data),
            (SLALevel._MAX, diagonal),
        ]

    def get_agents_from_click(
        self, click_data: Optional[Dict[str, Any]]
    ) -> Tuple[Optional[AgentID], Optional[AgentID]]:
        if click_data is None:
            return None, None

        to_agent = self._agents.get_by_name(click_data["points"][0]["x"])
        from_agent = self._agents.get_by_name(click_data["points"][0]["y"])
        logging.debug(
            "click: x: %s y: %s from: %s to: %s",
            click_data["points"][0]["x"],
            click_data["points"][0]["y"],
            from_agent.id,
            to_agent.id,
        )
        return from_agent.id, to_agent.id
