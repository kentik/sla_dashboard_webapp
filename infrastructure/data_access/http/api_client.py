# the below "disable=E0611" is needed as we don't commit the generated code into git repo and thus CI linter complains
# pylint: disable=E0611
from generated.synthetics_http_client.synthetics import ApiClient, Configuration
from generated.synthetics_http_client.synthetics.api.synthetics_admin_service_api import SyntheticsAdminServiceApi
from generated.synthetics_http_client.synthetics.api.synthetics_data_service_api import SyntheticsDataServiceApi

# pylint: enable=E0611


class KentikAPI:
    def __init__(self, email: str, token: str, synthetics_url: str = "https://synthetics.api.kentik.com") -> None:
        configuration = Configuration(host=synthetics_url)
        configuration.api_key["email"] = email
        configuration.api_key["token"] = token
        client = ApiClient(configuration)
        self.synthetics_admin_service = SyntheticsAdminServiceApi(client)
        self.synthetics_data_service = SyntheticsDataServiceApi(client)
