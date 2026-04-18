"""Tests for GristDocument, list_documents(), find_document() in GristAPI."""
import pytest
from unittest.mock import patch, MagicMock
from core.grist_api import GristAPI, GristDocument, GristConnectionError


@pytest.fixture
def mock_session():
    with patch("requests.Session") as mock_session_cls:
        session = MagicMock()
        mock_session_cls.return_value = session
        yield session


@pytest.fixture
def api(mock_session):
    """GristAPI with org + workspace discovery pre-seeded."""
    a = GristAPI("http://localhost:8484", "test-key")
    a._org_id = "2"
    from core.grist_api import GristWorkspace
    a._all_workspaces = [
        GristWorkspace({"id": 10, "name": "Home", "orgDomain": ""}),
        GristWorkspace({"id": 20, "name": "Team", "orgDomain": ""}),
    ]
    return a


class TestGristDocument:
    def test_fields_set_from_dict(self):
        doc = GristDocument({"id": "abc123", "name": "My Sheet"}, workspace_id=10, workspace_name="Home")
        assert doc.id == "abc123"
        assert doc.name == "My Sheet"
        assert doc.workspace_id == 10
        assert doc.workspace_name == "Home"


class TestListDocuments:
    def _make_response(self, docs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"docs": docs}
        resp.raise_for_status.return_value = None
        return resp

    def test_returns_all_docs_across_workspaces(self, api, mock_session):
        mock_session.request.side_effect = [
            self._make_response([{"id": "doc1", "name": "Sheet A"}]),
            self._make_response([{"id": "doc2", "name": "Sheet B"}]),
        ]
        docs = api.list_documents()
        assert len(docs) == 2
        assert docs[0].id == "doc1"
        assert docs[0].workspace_name == "Home"
        assert docs[1].id == "doc2"
        assert docs[1].workspace_name == "Team"

    def test_scoped_to_workspace_by_name(self, api, mock_session):
        mock_session.request.return_value = self._make_response(
            [{"id": "doc1", "name": "Sheet A"}]
        )
        docs = api.list_documents(workspace="Home")
        assert len(docs) == 1
        assert docs[0].workspace_name == "Home"
        assert mock_session.request.call_count == 1

    def test_unknown_workspace_name_raises(self, api):
        with pytest.raises(GristConnectionError) as exc_info:
            api.list_documents(workspace="NonExistent")
        assert "NonExistent" in str(exc_info.value)
        assert "Home" in str(exc_info.value)
        assert "Team" in str(exc_info.value)

    def test_returns_empty_when_no_docs(self, api, mock_session):
        mock_session.request.side_effect = [
            self._make_response([]),
            self._make_response([]),
        ]
        docs = api.list_documents()
        assert docs == []

    def test_calls_list_workspaces_on_cache_miss(self, mock_session):
        """When _all_workspaces is None, list_workspaces() is called first."""
        # Simulate what list_workspaces() returns via the session
        ws_response = MagicMock()
        ws_response.status_code = 200
        ws_response.raise_for_status.return_value = None
        ws_response.json.return_value = [{"id": 10, "name": "Home", "orgDomain": ""}]

        docs_response = MagicMock()
        docs_response.status_code = 200
        docs_response.raise_for_status.return_value = None
        docs_response.json.return_value = {"docs": [{"id": "doc1", "name": "Sheet A"}]}

        # First request = list_workspaces (GET /api/orgs/{id}/workspaces)
        # Second request = list_documents (GET /api/workspaces/{wsId})
        mock_session.request.side_effect = [ws_response, docs_response]

        a = GristAPI("http://localhost:8484", "test-key")
        a._org_id = "2"
        # _all_workspaces is intentionally NOT pre-seeded (None)
        assert a._all_workspaces is None

        docs = a.list_documents()
        assert len(docs) == 1
        assert docs[0].id == "doc1"
        # Confirm list_workspaces() was called (2 HTTP requests total, not 1)
        assert mock_session.request.call_count == 2


class TestFindDocument:
    def _make_response(self, docs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"docs": docs}
        resp.raise_for_status.return_value = None
        return resp

    def test_returns_matching_document(self, api, mock_session):
        mock_session.request.side_effect = [
            self._make_response([{"id": "doc1", "name": "Sheet A"}]),
            self._make_response([{"id": "doc2", "name": "Sheet B"}]),
        ]
        doc = api.find_document("Sheet B")
        assert doc.id == "doc2"
        assert doc.name == "Sheet B"
        assert doc.workspace_name == "Team"

    def test_missing_name_raises_with_listing(self, api, mock_session):
        mock_session.request.side_effect = [
            self._make_response([{"id": "doc1", "name": "Sheet A"}]),
            self._make_response([]),
        ]
        with pytest.raises(GristConnectionError) as exc_info:
            api.find_document("Missing Doc")
        assert "Missing Doc" in str(exc_info.value)
        assert "Sheet A" in str(exc_info.value)

    def test_scoped_to_workspace(self, api, mock_session):
        mock_session.request.return_value = self._make_response(
            [{"id": "doc1", "name": "Sheet A"}]
        )
        doc = api.find_document("Sheet A", workspace="Home")
        assert doc.id == "doc1"
        assert mock_session.request.call_count == 1

    def test_name_not_in_scoped_workspace_raises(self, api, mock_session):
        mock_session.request.return_value = self._make_response(
            [{"id": "doc1", "name": "Sheet A"}]
        )
        with pytest.raises(GristConnectionError) as exc_info:
            api.find_document("Sheet B", workspace="Home")
        assert "Sheet B" in str(exc_info.value)
        assert "Sheet A" in str(exc_info.value)
