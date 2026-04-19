"""Dispatcher API REST Grist.

Module principal pour interagir avec l'API REST de Grist.
Gère la découverte d'org/workspace, la création de documents,
tables, colonnes, records.

Conforme à la documentation Grist REST API :
https://support.getgrist.com/api/

Flux de découverte :
  1. GET /api/orgs → obtenir orgId (ex: 2)
  2. GET /api/orgs/{orgId}/workspaces → obtenir workspaceId (ex: 2 "Home")
  3. POST /api/docs → créer doc avec workspaceId dans body
  4. POST /api/docs/{docId}/tables → créer table
  5. POST /api/docs/{docId}/tables/{tableId}/columns → créer colonnes
  6. POST /api/docs/{docId}/tables/{tableId}/records → ajouter records
"""

import json
import math
import time
import requests
from typing import Dict, List, Any, Optional


def _clean_value(v):
    """Clean value for JSON serialization: convert NaN/inf to None."""
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
    return v


# ============================================================================
# Exceptions personnalisées
# ============================================================================

class GristError(Exception):
    """Erreur Grist générique."""
    pass


class GristConnectionError(GristError):
    """Impossible de joindre le serveur Grist."""
    pass


class GristAuthError(GristError):
    """Authentification échouée (401/403)."""
    pass


class GristAPIError(GristError):
    """Erreur retournée par l'API Grist."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")


# ============================================================================
# Data classes
# ============================================================================

class GristOrg:
    """Représentation d'un org Grist."""
    def __init__(self, data: Dict[str, Any]):
        self.id: str = str(data["id"])
        self.name: str = data.get("name", "")
        self.domain: str = data.get("domain", "")


class GristWorkspace:
    """Représentation d'un workspace Grist."""
    def __init__(self, data: Dict[str, Any]):
        self.id: int = data["id"]
        self.name: str = data.get("name", "")
        self.org_domain: str = data.get("orgDomain", "")
        self.is_support: bool = data.get("isSupportWorkspace", False)


class GristDocument:
    """Représentation d'un document Grist."""
    def __init__(self, data: Dict[str, Any], workspace_id: int, workspace_name: str):
        self.id: str = str(data["id"])
        self.name: str = data.get("name", "")
        self.workspace_id: int = workspace_id
        self.workspace_name: str = workspace_name


# ============================================================================
# Client API Grist
# ============================================================================

class GristAPI:
    """Client pour l'API REST Grist.

    Découvre automatiquement l'org et le workspace par défaut.
    Routes :
      /api/orgs → orgs
      /api/orgs/{orgId}/workspaces → workspaces
      /api/docs → créer doc
      /api/docs/{docId}/tables → tables
      /api/docs/{docId}/tables/{tid}/columns → colonnes
      /api/docs/{docId}/tables/{tid}/records → records

    Inclut un retry exponentiel sur les erreurs transitoires.
    """

    MAX_RETRIES = 3
    TIMEOUT = 30

    def __init__(
        self,
        server: str,
        api_key: str,
        api_prefix: str = "",
    ):
        """Initialiser le client Grist.

        Args:
            server: URL de base du serveur Grist
            api_key: Clé API Grist (Bearer token)
            api_prefix: Prefix API (vide pour self-hosted direct,
                        "/o" si derrière un proxy avec prefix)
        """
        self.server = server.rstrip("/")
        self.api_key = api_key
        self.api_prefix = api_prefix
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        # Cache de découverte
        self._org_id: Optional[str] = None
        self._workspace_id: Optional[int] = None
        self._workspace_name: Optional[str] = None
        self._all_workspaces: Optional[List[GristWorkspace]] = None
        self._widgets_cache: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # Helpers URL
    # ------------------------------------------------------------------

    def _api_url(self, path: str) -> str:
        """Construire l'URL complète pour un endpoint API.

        Ex: _api_url("/api/orgs") → http://localhost:8484/api/orgs
        """
        parts = [self.server.rstrip("/")]
        if self.api_prefix:
            parts.append(self.api_prefix.strip("/"))
        parts.append(path.strip("/"))
        return "/".join(parts)

    def _get_org_id(self) -> str:
        """Retourner l'orgId courant (cache le résultat).

        Retourne le premier org trouvé via GET /api/orgs.
        """
        if self._org_id is not None:
            return self._org_id

        try:
            response = self._request_with_retry(
                "GET", self._api_url("/api/orgs")
            )
            orgs = response.json()
            if not orgs:
                raise GristConnectionError(
                    "Aucun org trouvé sur le serveur Grist"
                )
            self._org_id = str(orgs[0]["id"])
            return self._org_id
        except (GristConnectionError, GristAuthError):
            raise
        except Exception:
            raise GristConnectionError("Impossible de récupérer l'orgId")

    def _get_workspace_id(self) -> int:
        """Retourner le workspaceId courant (découverte automatique).

        Si un workspace a été explicitement défini via set_workspace(),
        le retourne directement. Sinon, découvre le premier workspace
        de l'org (généralement "Home").
        """
        if self._workspace_id is not None:
            return self._workspace_id

        # Découvrir les workspaces
        workspaces = self.list_workspaces()
        if not workspaces:
            raise GristConnectionError(
                "Aucun workspace trouvé dans l'org"
            )
        # Prefer "Home" workspace; fall back to first non-support workspace
        user_ws = [w for w in workspaces if not w.is_support]
        home_ws = next((w for w in user_ws if w.name == "Home"), None)
        chosen = home_ws or (user_ws[0] if user_ws else workspaces[0])
        self._workspace_id = chosen.id
        self._workspace_name = chosen.name
        return self._workspace_id

    def _doc_url(self, doc_id: str, path: str = "") -> str:
        """Construire une URL pour un document spécifique.

        Route: /api/docs/{docId}[/{path}]
        """
        clean_path = path.lstrip("/")
        if clean_path:
            return self._api_url(f"/api/docs/{doc_id}/{clean_path}")
        return self._api_url(f"/api/docs/{doc_id}")

    def _ws_url(self, path: str) -> str:
        """Construire une URL pour un workspace spécifique.

        Route: /api/workspaces/{workspaceId}[/{path}]
        """
        ws_id = self._get_workspace_id()
        clean_path = path.lstrip("/")
        if clean_path:
            return self._api_url(f"/api/workspaces/{ws_id}/{clean_path}")
        return self._api_url(f"/api/workspaces/{ws_id}")

    # ------------------------------------------------------------------
    # Découverte Org & Workspace
    # ------------------------------------------------------------------

    def list_orgs(self) -> List[GristOrg]:
        """Lister tous les orgs accessibles.

        GET /api/orgs

        Returns:
            Liste de GristOrg
        """
        response = self._request_with_retry(
            "GET", self._api_url("/api/orgs")
        )
        orgs_data = response.json()
        return [GristOrg(o) for o in orgs_data]

    def list_workspaces(self) -> List[GristWorkspace]:
        """Lister les workspaces de l'org courant.

        GET /api/orgs/{orgId}/workspaces

        Returns:
            Liste de GristWorkspace
        """
        org_id = self._get_org_id()
        response = self._request_with_retry(
            "GET",
            self._api_url(f"/api/orgs/{org_id}/workspaces")
        )
        ws_data = response.json()
        self._all_workspaces = [GristWorkspace(w) for w in ws_data]
        return self._all_workspaces

    def set_workspace(
        self,
        name: Optional[str] = None,
        workspace_id: Optional[int] = None,
    ) -> int:
        """Définir le workspace par défaut pour les créations de documents.

        Args:
            name: Nom du workspace (ex: "Home")
            workspace_id: ID du workspace

        Returns:
            L'ID du workspace sélectionné

        Raises:
            GristConnectionError: Si le workspace n'est pas trouvé
        """
        # Découvrir les workspaces si nécessaire
        if self._all_workspaces is None:
            self.list_workspaces()
        assert self._all_workspaces is not None

        if workspace_id is not None:
            self._workspace_id = workspace_id
            ws = next(
                (w for w in self._all_workspaces if w.id == workspace_id),
                None,
            )
            if ws:
                self._workspace_name = ws.name
            return workspace_id

        if name is not None:
            ws = next(
                (w for w in self._all_workspaces if w.name == name),
                None,
            )
            if ws:
                self._workspace_id = ws.id
                self._workspace_name = ws.name
                return ws.id

        raise GristConnectionError(
            f"Workspace non trouvé (nom='{name}', id={workspace_id}). "
            f"Workspaces disponibles: "
            f"{[w.name for w in self._all_workspaces]}"
        )

    def list_documents(
        self,
        workspace: Optional[str] = None,
    ) -> List[GristDocument]:
        """Lister les documents accessibles.

        GET /api/workspaces/{workspaceId}/docs

        Args:
            workspace: Nom du workspace à explorer. Si None, explore tous les
                       workspaces de l'org.

        Returns:
            Liste de GristDocument

        Raises:
            GristConnectionError: Si le nom de workspace donné est introuvable.
        """
        if self._all_workspaces is None:
            self.list_workspaces()
        assert self._all_workspaces is not None

        if workspace is not None:
            targets = [w for w in self._all_workspaces if w.name == workspace]
            if not targets:
                available = [w.name for w in self._all_workspaces]
                raise GristConnectionError(
                    f"Workspace '{workspace}' introuvable. "
                    f"Workspaces disponibles : {available}"
                )
        else:
            targets = list(self._all_workspaces)

        docs: List[GristDocument] = []
        for ws in targets:
            response = self._request_with_retry(
                "GET",
                self._api_url(f"/api/workspaces/{ws.id}"),
            )
            for doc_data in response.json().get("docs", []):
                docs.append(GristDocument(doc_data, workspace_id=ws.id, workspace_name=ws.name))
        return docs

    def find_document(
        self,
        name: str,
        workspace: Optional[str] = None,
    ) -> "GristDocument":
        """Trouver un document Grist par son nom.

        Args:
            name: Nom exact du document (sensible à la casse).
            workspace: Si fourni, cherche uniquement dans ce workspace.

        Returns:
            GristDocument correspondant au nom.

        Raises:
            GristConnectionError: Si aucun document ne correspond au nom,
                                  avec la liste des documents disponibles.
        """
        docs = self.list_documents(workspace=workspace)
        for doc in docs:
            if doc.name == name:
                return doc
        available = [d.name for d in docs]
        raise GristConnectionError(
            f"Document '{name}' introuvable. "
            f"Documents disponibles : {available}"
        )

    # ------------------------------------------------------------------
    # Excel Import & Internal Actions
    # ------------------------------------------------------------------

    def upload_excel(self, file_path: str) -> str:
        """Uploader un fichier Excel et créer un document Grist.

        POST /api/docs (binary xlsx content)

        Args:
            file_path: Chemin absolu ou relatif vers le fichier .xlsx

        Returns:
            docId du document créé (ex: "new~abc123~1")

        Raises:
            GristAPIError: Si la réponse n'est pas un docId string.
        """
        with open(file_path, "rb") as f:
            content = f.read()

        response = self._request_with_retry(
            "POST",
            self._api_url("/api/docs"),
            data=content,
            headers={
                "Content-Type": (
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"
                )
            },
        )
        doc_id = response.json()
        if not isinstance(doc_id, str):
            raise GristAPIError(200, f"Réponse upload inattendue: {doc_id}")
        return doc_id

    def apply_actions(self, doc_id: str, actions: list) -> dict:
        """Appliquer des actions internes Grist à un document.

        POST /api/docs/{docId}/apply
        Body: [[actionType, tableId, rowId, fields], ...]   ← bare JSON array, NOT wrapped in {"actions": ...}

        Args:
            doc_id: Identifiant du document cible
            actions: Liste d'actions Grist internes

        Returns:
            Réponse JSON de l'API (résultats des actions)
        """
        response = self._request_with_retry(
            "POST",
            self._doc_url(doc_id, "apply"),
            json=actions,
        )
        return response.json()

    def list_widgets(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Lister les widgets officiels et communautaires exposés par Grist.

        GET /api/widgets
        """
        if self._widgets_cache is not None and not force_refresh:
            return self._widgets_cache

        response = self._request_with_retry(
            "GET",
            self._api_url("/api/widgets"),
        )
        data = response.json()
        if not isinstance(data, list):
            raise GristAPIError(200, f"Réponse widgets inattendue: {json.dumps(data)[:200]}")
        self._widgets_cache = data
        return data

    def get_widget(
        self,
        widget_id: str,
        plugin_id: str = "",
        *,
        force_refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Retourner la définition d'un widget par son identifiant."""
        widgets = self.list_widgets(force_refresh=force_refresh)
        exact_match: Optional[Dict[str, Any]] = None
        fallback_match: Optional[Dict[str, Any]] = None

        for widget in widgets:
            if widget.get("widgetId") != widget_id:
                continue
            current_plugin_id = widget.get("source", {}).get("pluginId", "")
            if plugin_id and current_plugin_id == plugin_id:
                exact_match = widget
                break
            if not plugin_id and current_plugin_id == "":
                exact_match = widget
                break
            if fallback_match is None:
                fallback_match = widget

        return exact_match or fallback_match

    # ------------------------------------------------------------------
    # Normalisation des types Grist
    # ------------------------------------------------------------------

    GRIST_TYPE_MAP: Dict[str, str] = {
        # aliases → canonical Grist API types
        "Integer": "Int",
        "Int": "Int",
        "Float": "Numeric",
        "Numeric": "Numeric",
        "Bool": "Toggle",
        "Toggle": "Toggle",
        "Ref": "Reference",
        "Reference": "Reference",
        "Reference List": "RefList",
        "RefList": "RefList",
        "Choice": "Choice",
        "ChoiceList": "ChoiceList",
        "Attachment": "Attachment",
        "DateTime": "DateTime",
        "Date": "Date",
        "Text": "Text",
    }

    @staticmethod
    def normalize_grist_type(type_name: str) -> str:
        """Convertir un type vers le vrai type Grist API.

        Mapping : Int→Integer, Float→Numeric, Bool→Toggle, Ref→Reference
        Garde inchangés les types déjà corrects (Text, Date, etc.)
        """
        return GristAPI.GRIST_TYPE_MAP.get(type_name, type_name)



    # ------------------------------------------------------------------
    # Méthode privée : requête avec retry exponentiel
    # ------------------------------------------------------------------

    def _request_with_retry(
        self, method: str, url: str, **kwargs
    ) -> requests.Response:
        """Exécuter une requête HTTP avec retry exponentiel.

        Retries sur ConnectionError, Timeout, HTTP 5xx.
        Pas de retry sur 401/403.
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.request(
                    method, url,
                    timeout=self.TIMEOUT,
                    **kwargs,
                )
                response.raise_for_status()
                return response

            except requests.ConnectionError:
                if attempt == self.MAX_RETRIES - 1:
                    raise GristConnectionError(
                        f"Impossible de joindre le serveur Grist ({url})"
                    )
                time.sleep(2 ** attempt)

            except requests.Timeout:
                if attempt == self.MAX_RETRIES - 1:
                    raise GristConnectionError(
                        f"Timeout lors de l'appel à {url}"
                    )
                time.sleep(2 ** attempt)

            except requests.HTTPError as e:
                status = (
                    e.response.status_code if e.response is not None else 0
                )
                if status in (401, 403):
                    raise GristAuthError(
                        "Clé API invalide ou non autorisée"
                    )
                if status >= 500:
                    if attempt == self.MAX_RETRIES - 1:
                        raise GristAPIError(status, str(e))
                    time.sleep(2 ** attempt)
                else:
                    raise GristAPIError(status, str(e))

        raise GristConnectionError(f"Failed after {self.MAX_RETRIES} retries: {url}")

    # ------------------------------------------------------------------
    # Document Lifecycle
    # ------------------------------------------------------------------

    def test_connection(self) -> bool:
        """Vérifier la connectivité avec le serveur Grist.

        GET /api/orgs
        """
        try:
            response = self._request_with_retry(
                "GET", self._api_url("/api/orgs")
            )
            return response.status_code == 200
        except (GristConnectionError, GristAuthError):
            raise
        except Exception:
            raise GristConnectionError("Impossible de joindre le serveur Grist")

    def create_document(
        self,
        name: str = "Import Excel",
        workspace_id: Optional[int] = None,
    ) -> str:
        """Créer un document Grist.

        POST /api/workspaces/{workspaceId}/docs
        Body: {"name": "...", "isPinned": false}

        Args:
            name: Nom du document à créer
            workspace_id: ID du workspace. Si None, utilise le workspace
                         par défaut (découvert automatiquement).

        Returns:
            docId du document créé (string)
        """
        ws_id = workspace_id if workspace_id is not None else self._get_workspace_id()

        response = self._request_with_retry(
            "POST",
            self._api_url(f"/api/workspaces/{ws_id}/docs"),
            json={"name": name, "isPinned": False},
        )
        data = response.json()
        if isinstance(data, str):
            return data
        return data.get("docId", data.get("id", str(data)))

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def delete_table(self, doc_id: str, table_id: str) -> None:
        """Delete a table from a Grist document via internal action.

        Uses apply_actions with RemoveTable — the only supported deletion path.
        Silent no-op if table does not exist.
        """
        try:
            self.apply_actions(doc_id, [["RemoveTable", table_id]])
        except GristAPIError:
            pass

    def create_table(self, doc_id: str, table_id: str, columns: Optional[List[Dict[str, Any]]] = None) -> None:
        """Créer une table dans un document Grist.

        POST /api/docs/{docId}/tables
        Body: {"tables": [{"id": "TableName", "columns": [...]}]}
        
        Note: Grist requires columns to be specified at table creation time.
        """
        table_columns = columns if columns else []
        table_def: Dict[str, Any] = {"id": table_id, "columns": table_columns}
        self._request_with_retry(
            "POST",
            self._doc_url(doc_id, "tables"),
            json={"tables": [table_def]},
        )

    # ------------------------------------------------------------------
    # Colonnes
    # ------------------------------------------------------------------

    def add_columns(
        self,
        doc_id: str,
        table_id: str,
        columns: List[Dict[str, Any]],
    ) -> None:
        """Ajouter des colonnes à une table Grist.

        POST /api/docs/{docId}/tables/{tableId}/columns
        Body: {"columns": [{"id": "colId", "fields": {...}}, ...]}
        """
        self._request_with_retry(
            "POST",
            self._doc_url(doc_id, f"tables/{table_id}/columns"),
            json={"columns": columns},
        )

    def patch_columns(
        self,
        doc_id: str,
        table_id: str,
        columns: List[Dict[str, Any]],
    ) -> None:
        """Modifier des colonnes existantes dans une table Grist.

        PATCH /api/docs/{docId}/tables/{tableId}/columns
        Body: {"columns": [{"id": "colId", "fields": {...}}, ...]}
        """
        self._request_with_retry(
            "PATCH",
            self._doc_url(doc_id, f"tables/{table_id}/columns"),
            json={"columns": columns},
        )

    def add_column(
        self,
        doc_id: str,
        table_id: str,
        col_id: str,
        col_type: str,
        **kwargs,
    ) -> None:
        """Ajouter une colonne à une table Grist (facilité).

        Args:
            doc_id: Identifiant du document
            table_id: Identifiant de la table
            col_id: Identifiant de la colonne
            col_type: Type Grist (Text, Integer, Numeric, Date, Toggle, Reference)
            **kwargs: column (pour Ref), formula, label
        """
        normalized_type = GristAPI.normalize_grist_type(col_type)
        fields: Dict[str, Any] = {"type": normalized_type}

        if "column" in kwargs:
            fields["column"] = kwargs["column"]
        if "formula" in kwargs:
            fields["formula"] = kwargs["formula"]
            fields["isFormula"] = True
        if "label" in kwargs:
            fields["label"] = kwargs["label"]

        self.add_columns(doc_id, table_id, [
            {"id": col_id, "fields": fields}
        ])

    # ------------------------------------------------------------------
    # Records
    # ------------------------------------------------------------------

    def add_records(
        self,
        doc_id: str,
        table_id: str,
        records: List[Dict],
        chunk_size: int = 100,
    ) -> int:
        """Ajouter des records en batch.

        POST /api/docs/{docId}/tables/{tableId}/records
        Body: {"records": [{"fields": {...}}, ...]}
        """
        valid_cols = self.get_columns(doc_id, table_id)
        valid_col_ids = {c["id"] for c in valid_cols}
        
        total_added = 0
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            grist_records = []
            for record in chunk:
                fields = {
                    k: _clean_value(v) 
                    for k, v in record.items() 
                    if k != "id" and k in valid_col_ids
                }
                grist_records.append({"fields": fields})
            self._request_with_retry(
                "POST",
                self._doc_url(doc_id, f"tables/{table_id}/records"),
                json={"records": grist_records},
            )
            total_added += len(chunk)
        return total_added

    def update_records(
        self,
        doc_id: str,
        table_id: str,
        records: List[Dict],
    ) -> None:
        """Modifier des records existants.

        PATCH /api/docs/{docId}/tables/{tableId}/records
        Body: {"records": [{"id": N, "fields": {...}}, ...]}
        """
        self._request_with_retry(
            "PATCH",
            self._doc_url(doc_id, f"tables/{table_id}/records"),
            json={"records": records},
        )

    def upsert_records(
        self,
        doc_id: str,
        table_id: str,
        records: List[Dict],
    ) -> None:
        """Ajouter ou mettre à jour des records (upsert).

        PUT /api/docs/{docId}/tables/{tableId}/records
        Body: {"records": [{"require": {...}, "fields": {...}}, ...]}
        """
        self._request_with_retry(
            "PUT",
            self._doc_url(doc_id, f"tables/{table_id}/records"),
            json={"records": records},
        )

    def delete_records(
        self,
        doc_id: str,
        table_id: str,
        record_ids: List[int],
    ) -> None:
        """Supprimer des records d'une table.

        POST /api/docs/{docId}/tables/{tableId}/records/delete
        Body: [1, 2, 3]
        """
        self._request_with_retry(
            "POST",
            self._doc_url(doc_id, f"tables/{table_id}/records/delete"),
            json=record_ids,
        )

    def get_records(
        self,
        doc_id: str,
        table_id: str,
        filter: Optional[str] = None,
        sort: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict]:
        """Récupérer des records d'une table.

        GET /api/docs/{docId}/tables/{tableId}/records
        Query params: filter, sort, limit
        """
        params = {}
        if filter is not None:
            params["filter"] = filter
        if sort is not None:
            params["sort"] = sort
        if limit is not None:
            params["limit"] = limit

        response = self._request_with_retry(
            "GET",
            self._doc_url(doc_id, f"tables/{table_id}/records"),
            params=params,
        )
        data = response.json()
        return data.get("records", [])

    def get_tables(
        self,
        doc_id: str,
    ) -> List[Dict[str, Any]]:
        """Récupérer toutes les tables d'un document Grist.

        GET /api/docs/{docId}/tables

        Returns:
            Liste de dicts avec structure:
            [{"id": "Table1", "label": "Table 1"}, ...]
        """
        response = self._request_with_retry(
            "GET",
            self._doc_url(doc_id, "tables"),
        )
        data = response.json()
        return data.get("tables", [])

    def get_columns(
        self,
        doc_id: str,
        table_id: str,
    ) -> List[Dict[str, Any]]:
        """Récupérer les colonnes d'une table.

        GET /api/docs/{docId}/tables/{tableId}/columns

        Returns:
            Liste de dicts: [{"id": "colId", "fields": {"type": "...", "label": "..."}}, ...]
        """
        response = self._request_with_retry(
            "GET",
            self._doc_url(doc_id, f"tables/{table_id}/columns"),
        )
        data = response.json()
        return data.get("columns", [])

