import dash_core_components as dcc
import dash_html_components as html


class IndexView:
    """Represents the main page template; header, footer, content place holder"""

    URL = "url"
    PAGE_CONTENT = "page-content"
    MATRIX_REDIRECT = "matrix-click-redirect"
    METRIC_REDIRECT = "metric-selector-redirect"

    @staticmethod
    def make_layout() -> html.Div:
        return html.Div(
            [
                # doesn't render anything, represents the URL bar
                dcc.Location(id=IndexView.URL, refresh=True),
                # doesn't render anything, enables redirections
                html.Div(id=IndexView.MATRIX_REDIRECT),
                html.Div(id=IndexView.METRIC_REDIRECT),
                # content will be rendered in this element
                dcc.Loading(
                    id=IndexView.PAGE_CONTENT,
                    type="default",
                    fullscreen=True,
                ),
            ]
        )
