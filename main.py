import logging
import os
import sys
from typing import Tuple
from urllib.parse import quote, unquote

import dash
import flask
from dash import dcc, html
from dash.dependencies import ClientsideFunction, Input, Output

import routing

from domain.cache.caching_repo_request_driven import CachingRepoRequestDriven
from domain.metric import MetricType
from infrastructure.config import ConfigYAML
from infrastructure.data_access.http.synthetics_repo import SyntheticsRepo
from presentation.http_error_view import HTTPErrorView
from presentation.index_view import IndexView
from presentation.matrix_view import MatrixView
from presentation.time_series_view import TimeSeriesView

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
            self._cached_repo = CachingRepoRequestDriven(
                repo,
                config.test_id,
                config.data_request_interval_periods,
                config.data_history_length_periods,
                config.data_min_periods,
            )

            # routing
            self._routes = {
                routing.MAIN: lambda _: self._make_matrix_layout(routing.encode_matrix_path(MetricType.LATENCY)),
                routing.MATRIX: self._make_matrix_layout,
                routing.TIME_SERIES: self._make_time_series_layout,
            }

            # views
            self._matrix_view = MatrixView(config)
            self._time_series_view = TimeSeriesView(config)

            # web framework configuration
            app = dash.Dash(
                __name__,
                suppress_callback_exceptions=True,
                title="SLA Dashboard",
                update_title="Loading test results...",
                assets_folder="data/assets",
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
                return dcc.Location(id="MATRIX", pathname=path, refresh=True)

            # auto-refresh checkbox, will call client-side function
            app.clientside_callback(
                ClientsideFunction(namespace="clientside", function_name="auto_refresh"),
                Output(IndexView.DISREGARD_AUTO_REFRESH_OUTPUT, "title"),
                [Input(MatrixView.AUTO_REFRESH_CHECKBOX, "value")],
            )

        except Exception:
            logger.exception("WebApp initialization failure")
            sys.exit(1)

    def get_production_server(self) -> flask.Flask:
        return self._app.server

    def run_development_server(self) -> None:
        self._app.run_server(debug=True)

    def _make_matrix_layout(self, path: str) -> html.Div:
        metric = routing.decode_matrix_path(path)
        results = self._cached_repo.get_mesh_results_all_connections()
        config = self._cached_repo.get_mesh_config()
        data_history_seconds = self._cached_repo.min_history_seconds
        return self._matrix_view.make_layout(results, config, data_history_seconds, metric)

    def _make_time_series_layout(self, path: str) -> html.Div:
        from_agent, to_agent = routing.decode_time_series_path(path)
        results = self._cached_repo.get_mesh_results_single_connection(from_agent, to_agent)
        config = self._cached_repo.get_mesh_config()
        return self._time_series_view.make_layout(from_agent, to_agent, results, config)


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
