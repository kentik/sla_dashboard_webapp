from typing import List, Optional, Tuple

import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go

from domain.config import Config
from domain.geo import calc_distance
from domain.metric import MetricType
from domain.model import MeshResults
from domain.types import AgentID


class ChartView:
    def __init__(self, config: Config) -> None:
        self._config = config

    def make_layout(self, from_agent: AgentID, to_agent: AgentID, mesh: MeshResults) -> html.Div:
        title = self.make_title(from_agent, to_agent, mesh)
        conn = mesh.connection(from_agent, to_agent)

        if conn.has_data():
            content = self.make_charts_content(from_agent, to_agent, mesh)
        else:
            content = self.make_no_data_content()

        return html.Div(
            children=[
                html.H1(children=title, className="header_main"),
                html.Div(children=content, className="main_container"),
            ]
        )

    @staticmethod
    def make_no_data_content() -> List:
        return [html.H1("NO DATA"), html.Br(), html.Br()]

    def make_charts_content(self, from_agent: AgentID, to_agent: AgentID, mesh: MeshResults) -> List:
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

    def make_title(self, from_agent_id: AgentID, to_agent_id: AgentID, mesh: MeshResults) -> str:
        from_agent = mesh.agents.get_by_id(from_agent_id)
        to_agent = mesh.agents.get_by_id(to_agent_id)
        distance_unit = self._config.distance_unit
        distance = calc_distance(from_agent.coords, to_agent.coords, distance_unit)
        return (
            f"{from_agent.name}, {from_agent.alias} [{from_agent.id}] -> "
            f"{to_agent.name}, {to_agent.alias} [{to_agent.id}] ({distance:.0f} {distance_unit.value})"
        )

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
        fig = go.Figure(data=[go.Scatter(x=xdata, y=ydata)], layout=layout, layout_yaxis_range=y_range)
        fig.update_yaxes(rangemode="tozero")  # make the y-scale start from 0
        return fig
