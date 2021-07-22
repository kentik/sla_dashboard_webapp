import logging
import os
import sys
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote, unquote

import dash
import dash_core_components as dcc
import dash_html_components as html
import flask
from dash.dependencies import Input, Output

import routing

from domain.cached_repo_request_driven import CachedRepoRequestDriven
from domain.metric_type import MetricType
from infrastructure.config import ConfigYAML
from infrastructure.data_access.http.synthetics_repo import SyntheticsRepo
from presentation.chart_view import ChartView
from presentation.http_error_view import HTTPErrorView
from presentation.index_view import IndexView
from presentation.matrix_view import MatrixView

FORMAT = "[%(asctime)-15s] [%(process)d] [%(levelname)s]  %(message)s"
logger = logging.getLogger(__name__)


class WebApp:
    def __init__(self) -> None:
        try:
            # app configuration
            config = ConfigYAML("data/config.yaml")
            self._config = config
            email, token = get_auth_email_token()
            api_server_url = os.getenv("KTAPI_URL")

            # logging
            logging.basicConfig(level=config.logging_level, format=FORMAT)

            # data access
            repo = SyntheticsRepo(email, token, api_server_url, config.timeout)
            self._cached_repo = CachedRepoRequestDriven(
                repo, config.test_id, config.data_update_period_seconds, config.data_update_lookback_seconds
            )

            # routing
            self._routes = {
                routing.MAIN: lambda _: self._make_matrix_layout(routing.encode_matrix_path(MetricType.LATENCY)),
                routing.MATRIX: self._make_matrix_layout,
                routing.CHART: self._make_chart_layout,
            }

            # views
            self._matrix_view = MatrixView(config)
            self._chart_view = ChartView(config)

            # web framework configuration
            app = dash.Dash(
                __name__,
                suppress_callback_exceptions=True,
                title="SLA Dashboard",
                update_title="Loading test results...",
                assets_folder="data",
            )
            app.layout = IndexView.make_layout()
            self._app = app

            # all views - handle path change
            @app.callback(Output(IndexView.PAGE_CONTENT, "children"), [Input(IndexView.URL, "pathname")])
            def display_page(pathname: str):
                pathname = unquote(pathname)
                try:
                    path_args = pathname.split("?", maxsplit=1)
                    make_layout = self._routes.get(path_args[0], lambda _: HTTPErrorView.make_layout(404))
                    return make_layout(pathname)
                except Exception:
                    logger.exception("Error while rendering page")
                    return HTTPErrorView.make_layout(500)

            # matrix view - handle metric select
            @app.callback(Output(IndexView.METRIC_REDIRECT, "children"), [Input(MatrixView.METRIC_SELECTOR, "value")])
            def update_matrix(metric_name: str):
                metric = MetricType(metric_name)
                path = quote(routing.encode_matrix_path(metric))
                return dcc.Location(id=IndexView.URL, pathname=path, refresh=True)

            # matrix view - handle cell click
            @app.callback(Output(IndexView.MATRIX_REDIRECT, "children"), Input(MatrixView.MATRIX, "clickData"))
            def open_chart(click_data: Optional[Dict[str, Any]]):
                from_agent, to_agent = self._matrix_view.get_agents_from_click(click_data)
                if from_agent is None or to_agent is None or from_agent == to_agent:
                    return None

                path = quote(routing.encode_chart_path(from_agent, to_agent))
                return dcc.Location(id=IndexView.URL, pathname=path, refresh=True)

        except Exception:
            logger.exception("WebApp initialization failure")
            sys.exit(1)

    def get_production_server(self) -> flask.Flask:
        return self._app.server

    def run_development_server(self) -> None:
        self._app.run_server(debug=True)

    def _make_matrix_layout(self, path: str) -> html.Div:
        metric = routing.decode_matrix_path(path)
        results = self._cached_repo.get_mesh_test_results()
        return self._matrix_view.make_layout(results, metric, self._config)

    def _make_chart_layout(self, path: str) -> html.Div:
        from_agent, to_agent = routing.decode_chart_path(path)
        results = self._cached_repo.get_mesh_test_results()
        return self._chart_view.make_layout(from_agent, to_agent, results)

    @property
    def callback(self):
        return self._app.callback


def get_auth_email_token() -> Tuple[str, str]:
    try:
        return os.environ["KTAPI_AUTH_EMAIL"], os.environ["KTAPI_AUTH_TOKEN"]
    except KeyError as err:
        raise Exception(f"{err} environment variable is missing")


# Run production server: gunicorn --workers=1 'main:run()'
def run() -> flask.Flask:
    app = WebApp()
    return app.get_production_server()


# Run development server: python main.py
if __name__ == "__main__":
    app = WebApp()
    app.run_development_server()
