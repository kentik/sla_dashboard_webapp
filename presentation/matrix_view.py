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
from domain.model.mesh_results import Agents, HealthItem
from domain.types import AgentID, Threshold

# Connections are displayed as a matrix using dcc.Graph component.
# The Graph is configured as a heatmap.
# In heatmap, each cell is assigned a floating-point type value.
# The heatmap itself is assigned a color scale that maps range [0.0 - 1.0] to colors.
# The heatmap dynamiacally "stretches" it's color scale range to cover all cells values.
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


# SLALevelColumn represents SLALevel single column in connectin matrix
SLALevelColumn = List[Optional[SLALevel]]


class MatrixView:
    MATRIX = "matrix"
    METRIC_SELECTOR = "metric-selector"

    def __init__(self, config: Config) -> None:
        self._config = config
        self._agents = Agents()
        self._color_scale = self._make_color_scale()

    def make_layout(self, mesh: MeshResults, metric: MetricType, config: Config) -> html.Div:
        self._agents = mesh.agents  # remember agents used to make the layout for further processing
        timestamp_low_ISO = mesh.utc_timestamp_low.isoformat() if mesh.utc_timestamp_low else None
        timestamp_high_ISO = mesh.utc_timestamp_high.isoformat() if mesh.utc_timestamp_high else None
        header = "SLA Dashboard"
        fig = self.make_figure(mesh, metric)
        return html.Div(
            children=[
                html.H1(children=header, className="header_main"),
                html.Div(
                    children=[
                        html.H2(
                            children=[
                                html.Span("Data timestamp range: "),
                                html.Span(
                                    "<test_results_timestamp_low>",
                                    className="header-timestamp",
                                    id="timestamp-low",
                                    title=timestamp_low_ISO,
                                ),
                                html.Span(" - ", className="header-timestamp"),
                                html.Span(
                                    "<test_results_timestamp_high>",
                                    className="header-timestamp",
                                    id="timestamp-high",
                                    title=timestamp_high_ISO,
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
                                    dcc.Graph(id=self.MATRIX, figure=fig, responsive=True), className="chart__default"
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
                                        html.Label(
                                            "No data", className="chart_legend__label chart_legend__label_nodata"
                                        ),
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
                    ],
                    className="main_container",
                ),
            ]
        )

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

        x_labels = [mesh.agents.get_by_id(agent_id).alias for agent_id in mesh.connection_matrix.agent_ids]
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

    def make_sla_levels(self, mesh: MeshResults, type: MetricType) -> List[SLALevelColumn]:
        thresholds = self.get_thresholds(type)
        sla_levels: List[SLALevelColumn] = []

        for from_id in reversed(mesh.connection_matrix.agent_ids):
            sla_levels_col: SLALevelColumn = []
            for to_id in mesh.connection_matrix.agent_ids:
                if from_id == to_id:
                    continue
                warning = thresholds.warning(from_id, to_id)
                critical = thresholds.critical(from_id, to_id)
                health = mesh.connection(from_id, to_id).latest_measurement
                if health:
                    metric = health.get_metric(type)
                    sla_level = self.get_sla_level(metric.value, warning, critical)
                else:
                    sla_level = SLALevel.NODATA
                sla_levels_col.append(sla_level)
            sla_levels.append(sla_levels_col)

        # mark matrix diagonal, use alternating SLALevel._MIN and SLALevel._MAX
        # to ensure matrix contains values in full range 0..1 - to match the color scale
        for i in range(len(mesh.connection_matrix.agent_ids)):
            sla_levels[-(i + 1)].insert(i, SLALevel(i % 2))
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
        for from_id in reversed(mesh.connection_matrix.agent_ids):
            for to_id in mesh.connection_matrix.agent_ids:
                if from_id == to_id:
                    continue
                from_agent = mesh.agents.get_by_id(from_id)
                to_agent = mesh.agents.get_by_id(to_id)
                health = mesh.connection(from_agent.id, to_agent.id).latest_measurement
                text = cls.format_health(metric, health, False, "")
                annotations.append(
                    dict(showarrow=False, text=text, xref="x", yref="y", x=to_agent.alias, y=from_agent.alias)
                )
        return annotations

    @staticmethod
    def format_health(type: MetricType, health: Optional[HealthItem], include_unit: bool = False, nan="N/A") -> str:
        if not health:
            return nan

        metric = health.get_metric(type)
        if math.isnan(metric.value):
            return nan

        return "{:.2f}{}".format(metric.value, metric.unit if include_unit else "")

    def make_matrix_hover_text(self, mesh: MeshResults) -> List[List[str]]:
        # make hover text for each cell in the matrix
        matrix_hover_text: List[List[str]] = []
        for from_id in reversed(mesh.connection_matrix.agent_ids):
            column_hover_text: List[str] = []
            for to_id in mesh.connection_matrix.agent_ids:
                if from_id == to_id:
                    continue
                text = self.make_cell_hover_text(from_id, to_id, mesh)
                column_hover_text.append(text)
            matrix_hover_text.append(column_hover_text)

        # insert blank diagonal into matrix
        for i in range(len(mesh.connection_matrix.agent_ids)):
            matrix_hover_text[-(i + 1)].insert(i, "")

        return matrix_hover_text

    def make_cell_hover_text(self, from_agent_id, to_agent_id: AgentID, mesh: MeshResults) -> str:
        from_agent = mesh.agents.get_by_id(from_agent_id)
        to_agent = mesh.agents.get_by_id(to_agent_id)
        conn = mesh.connection(from_agent.id, to_agent.id)
        distance_unit = self._config.distance_unit
        distance = calc_distance(from_agent.coords, to_agent.coords, distance_unit)

        cell_hover_text: List[str] = []
        cell_hover_text.append(f"{from_agent.alias} -> {to_agent.alias}")
        cell_hover_text.append(f"Distance: {distance:.0f} {distance_unit.value}")

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

    def get_agents_from_click(self, clickData: Optional[Dict[str, Any]]) -> Tuple[Optional[AgentID], Optional[AgentID]]:
        if clickData is None:
            return None, None

        to_agent_alias, from_agent_alias = clickData["points"][0]["x"], clickData["points"][0]["y"]
        return self._agents.get_by_alias(from_agent_alias).id, self._agents.get_by_alias(to_agent_alias).id
