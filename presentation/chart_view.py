import urllib.parse as urlparse
from typing import List, Optional, Tuple
from urllib.parse import parse_qs

import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
from dash_html_components.Br import Br
from dash_html_components.Div import Div

from domain.config import Config
from domain.geo import calc_distance
from domain.metric_type import MetricType
from domain.model import MeshResults
from domain.types import AgentID


class ChartView:
    def __init__(self, config: Config) -> None:
        self._config = config

    def make_layout(self, from_agent, to_agent: AgentID, mesh: MeshResults) -> html.Div:
        title = self.make_title(from_agent, to_agent, mesh)
        conn = mesh.connection(from_agent, to_agent)

        if conn.is_no_data():
            content = self.make_no_data_content()
        else:
            content = self.make_charts_content(from_agent, to_agent, mesh)

        content.append(
            html.Div(
                html.Center(
                    dcc.Link("Back to matrix view", href="/"),
                    style={"font-size": "large"},
                ),
                className="button",
            )
        )

        return html.Div(
            children=[
                html.H1(children=title, className="header_main"),
                html.Div(
                    children=content,
                    className="main_container",
                ),
            ],
        )

    def make_no_data_content(self) -> List:
        return [
            html.H1("NO DATA"),
            html.Br(),
            html.Br(),
        ]

    def make_charts_content(self, from_agent, to_agent: AgentID, mesh: MeshResults) -> List:
        fig_latency = self.make_figure(from_agent, to_agent, MetricType.LATENCY, mesh)
        fig_jitter = self.make_figure(from_agent, to_agent, MetricType.JITTER, mesh)
        fig_packetloss = self.make_figure(from_agent, to_agent, MetricType.PACKET_LOSS, mesh, (0, 100))
        style = {"width": "100%", "height": "20vh", "display": "inline-block", "margin-bottom": "20px"}
        return [
            html.H3(children=MetricType.LATENCY.value, className="chart_title"),
            dcc.Graph(id="timeseries_latency_chart", style=style, figure=fig_latency),
            html.H3(children=MetricType.JITTER.value, className="chart_title"),
            dcc.Graph(id="timeseries_jitter_chart", style=style, figure=fig_jitter),
            html.H3(children=MetricType.PACKET_LOSS.value, className="chart_title"),
            dcc.Graph(id="timeseries_packetloss_chart", style=style, figure=fig_packetloss),
        ]

    def make_title(self, from_agent, to_agent: AgentID, mesh: MeshResults) -> str:
        from_alias = mesh.agents.get_alias(from_agent)
        to_alias = mesh.agents.get_alias(to_agent)
        from_coords = mesh.agents.get_by_id(from_agent).coords
        to_coords = mesh.agents.get_by_id(to_agent).coords
        distance_unit = self._config.distance_unit
        distance = calc_distance(from_coords, to_coords, distance_unit)
        return f"{from_alias} -> {to_alias} ({distance:.0f} {distance_unit.value})"

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
            margin={"t": 0, "b": 0}, modebar={"orientation": "v"}  # remove empty space above and below the chart
        )
        fig = go.Figure(
            data=[go.Scatter(x=xdata, y=ydata)],
            layout=layout,
            layout_yaxis_range=y_range,
        )
        fig.update_yaxes(rangemode="tozero")  # make the y-scale start from 0
        return fig

    @staticmethod
    def encode_path(from_agent, to_agent: AgentID) -> str:
        return f"/chart?from={from_agent}&to={to_agent}"

    @staticmethod
    def decode_path(path: str) -> Tuple[AgentID, AgentID]:
        params = urlparse.parse_qs(urlparse.urlparse(path).query)
        return params["from"][0], params["to"][0]
