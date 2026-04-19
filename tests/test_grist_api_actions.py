"""Tests for GristAPI.upload_excel() and GristAPI.apply_actions()."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from core.grist_api import GristAPI, GristAPIError


@pytest.fixture
def mock_session():
    with patch("requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        yield session


@pytest.fixture
def api(mock_session):
    a = GristAPI("http://localhost:8484", "test-key")
    a._org_id = "2"
    return a


def _resp(data, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


class TestUploadExcel:
    def test_returns_doc_id_string(self, api, mock_session, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"PK\x03\x04fake-xlsx-content")
        mock_session.request.return_value = _resp("new~abc123~1")

        doc_id = api.upload_excel(str(xlsx))

        assert doc_id == "new~abc123~1"

    def test_posts_to_api_docs_with_xlsx_content_type(self, api, mock_session, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        content = b"PK\x03\x04binary-content"
        xlsx.write_bytes(content)
        mock_session.request.return_value = _resp("new~abc123~1")

        api.upload_excel(str(xlsx))

        call_kwargs = mock_session.request.call_args
        assert call_kwargs[0][0] == "POST"
        assert "/api/docs" in call_kwargs[0][1]
        headers = call_kwargs[1].get("headers", {})
        assert "spreadsheetml" in headers.get("Content-Type", "")
        assert call_kwargs[1].get("data") == content

    def test_raises_on_non_string_response(self, api, mock_session, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        mock_session.request.return_value = _resp({"error": "bad"})

        with pytest.raises(GristAPIError):
            api.upload_excel(str(xlsx))


class TestApplyActions:
    def test_posts_actions_to_apply_endpoint(self, api, mock_session):
        mock_session.request.return_value = _resp({"results": []})
        actions = [["AddRecord", "_grist_Views", None, {"name": "Dashboard"}]]

        result = api.apply_actions("doc123", actions)

        call_kwargs = mock_session.request.call_args
        assert call_kwargs[0][0] == "POST"
        assert "doc123/apply" in call_kwargs[0][1]
        body = call_kwargs[1].get("json", {})
        assert body == actions

    def test_returns_response_json(self, api, mock_session):
        mock_session.request.return_value = _resp({"results": [1, 2]})

        result = api.apply_actions("doc123", [])

        assert result == {"results": [1, 2]}


class TestWidgets:
    def test_list_widgets_gets_widget_catalog(self, api, mock_session):
        mock_session.request.return_value = _resp([
            {"widgetId": "@gristlabs/widget-chart", "name": "Advanced charts", "url": "https://example.test/chart"},
        ])

        widgets = api.list_widgets()

        assert widgets[0]["widgetId"] == "@gristlabs/widget-chart"

    def test_get_widget_prefers_exact_plugin_match(self, api, mock_session):
        mock_session.request.return_value = _resp([
            {
                "widgetId": "same-id",
                "name": "Plugin version",
                "url": "https://example.test/plugin",
                "source": {"pluginId": "plugin-a"},
            },
            {
                "widgetId": "same-id",
                "name": "Hosted version",
                "url": "https://example.test/hosted",
                "source": {"pluginId": ""},
            },
        ])

        widget = api.get_widget("same-id", plugin_id="plugin-a")

        assert widget is not None
        assert widget["name"] == "Plugin version"
