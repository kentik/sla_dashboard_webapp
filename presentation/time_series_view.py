from typing import List, Optional, Tuple

import plotly.graph_objs as go
from dash import dcc, html

from domain.config import Config
from domain.geo import calc_distance
from domain.metric import MetricType
from domain.model import MeshConfig, MeshResults
from domain.types import AgentID


class TimeSeriesView:
    def __init__(self, config: Config) -> None:
        self._config = config

    def make_layout(self, from_agent: AgentID, to_agent: AgentID, results: MeshResults, config: MeshConfig) -> html.Div:
        title = self.make_title(from_agent, to_agent, config)
        conn = results.connection(from_agent, to_agent)

        if conn.has_data():
            content = self.make_time_series_content(from_agent, to_agent, results)
        else:
            content = self.make_no_data_content()

        return html.Div(
            children=[
                html.Div(children=title, className="main_header"),
                html.Div(children=content, className="main_container"),
            ]
        )

    @staticmethod
    def make_no_data_content() -> List:
        return [html.H1("NO DATA"), html.Br(), html.Br()]

    def make_time_series_content(self, from_agent: AgentID, to_agent: AgentID, mesh: MeshResults) -> List:
        fig_latency = self.make_figure(from_agent, to_agent, MetricType.LATENCY, mesh)
        fig_jitter = self.make_figure(from_agent, to_agent, MetricType.JITTER, mesh)
        fig_packetloss = self.make_figure(from_agent, to_agent, MetricType.PACKET_LOSS, mesh, (0, 100))
        style = {"width": "100%", "height": "20vh", "display": "inline-block", "margin-bottom": "20px"}
        return [
            html.H3(children=MetricType.PACKET_LOSS.value, className="time_series_title"),
            dcc.Graph(id="time_series_packet_loss", style=style, figure=fig_packetloss),
            html.H3(children=MetricType.LATENCY.value, className="time_series_title"),
            dcc.Graph(id="time_series_latency", style=style, figure=fig_latency),
            html.H3(children=MetricType.JITTER.value, className="time_series_title"),
            dcc.Graph(id="time_series_jitter", style=style, figure=fig_jitter),
        ]

    def make_title(self, from_agent_id: AgentID, to_agent_id: AgentID, config: MeshConfig) -> List:
        def label_cell(s: str) -> html.Td:
            return html.Td(className="time_series_header_label", children=s)

        def value_cell(s: str) -> html.Td:
            return html.Td(className="time_series_header_value", children=s)

        def row(label: str, value: str) -> html.Tr:
            return html.Tr([label_cell(label), value_cell(value)])

        from_agent = config.agents.get_by_id(from_agent_id)
        to_agent = config.agents.get_by_id(to_agent_id)
        distance_unit = self._config.distance_unit
        distance = calc_distance(from_agent.coords, to_agent.coords, distance_unit)
        return [
            html.Table(
                children=html.Tbody(
                    [
                        row(label, value)
                        for label, value in (
                            ("From:", f"{from_agent.name}, {from_agent.alias} [{from_agent.id}]"),
                            ("To:", f"{to_agent.name}, {to_agent.alias} [{to_agent.id}]"),
                            ("Distance:", f"{distance:.0f} {distance_unit.value}"),
                        )
                    ]
                )
            )
        ]

    @staticmethod
    def make_figure(
        from_agent,
        to_agent: AgentID,
        metric: MetricType,
        mesh: MeshResults,
        y_range: Optional[Tuple[float, float]] = None,
    ):
        filtered = mesh.filter(from_agent, to_agent, metric)
        xdata, ydata = zip(*filtered) if filtered else ((), ())
        layout = go.Layout(
            yaxis={"title": metric.unit, "range": y_range}, modebar={"orientation": "v"}, margin={"t": 0, "b": 0}
        )
        fig = go.Figure(data=[go.Scatter(x=xdata, y=ydata)], layout=layout)
        fig.update_yaxes(rangemode="tozero")  # make the y-scale start from 0
        return fig
