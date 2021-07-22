import json
import os
import sys
from logging import Logger

from flask import Flask, Response, request


def create_app() -> Flask:
    # create and configure the app
    app = Flask(__name__, instance_relative_config=False)

    # read predefined mesh test response from a file
    response_data = load_response_data(app.logger)

    # configure routes
    @app.route("/synthetics/v202101beta1/agents", methods=["GET"])
    def agents():
        return Response(
            response=json.dumps(response_data["agents-response"]),
            mimetype="application/json",
        )

    @app.route("/synthetics/v202101beta1/health/tests", methods=["POST"])
    def health_tests():
        return Response(
            response=json.dumps(response_data["health-tests-response"]),
            mimetype="application/json",
        )

    @app.route("/synthetics/v202101beta1/tests/<string:test_id>", methods=["GET"])
    def test(test_id: str):
        expected_test_id = response_data["test-response"]["test"]["id"]
        if test_id != expected_test_id:
            # Log error instead of returning Bad Request for ease of development
            app.logger.error(f"Requested test ID: {test_id}, expected: {expected_test_id}")

        return Response(
            response=json.dumps(response_data["test-response"]),
            mimetype="application/json",
        )

    @app.route("/shutdown", methods=["GET"])
    def shutdown():
        shutdown_func = request.environ.get("werkzeug.server.shutdown")
        if not shutdown_func:
            raise RuntimeError("Not running with the Werkzeug Server")
        shutdown_func()
        return Response(response="Server shutdown now", mimetype="text/html")

    return app


def load_response_data(logger: Logger) -> dict:
    response_file_path = os.getenv("RESPONSE_FILE_PATH")
    if not response_file_path:
        logger.critical('Environment variable "RESPONSE_FILE_PATH" is required')
        sys.exit(1)

    logger.info(f'Serving mesh test results from "{response_file_path}"')
    with open(response_file_path, mode="r") as f:
        return json.load(f)
