"""Grist Importer - upload Excel and verify document creation.

Thin layer over GristAPI.upload_excel() that:
1. Validates the file exists
2. Uploads the Excel binary to Grist
3. Verifies the resulting document has at least one table
4. Returns the docId for use by the Archetype Engine
"""

import os
from core.grist_api import GristAPI, GristConnectionError


class GristImporter:
    """Importe un fichier Excel dans Grist et verifie le resultat."""

    def __init__(self, api: GristAPI):
        self.api = api

    def import_excel(self, file_path: str) -> str:
        """Uploader un fichier Excel et retourner le docId verifie.

        Args:
            file_path: Chemin vers le fichier .xlsx

        Returns:
            docId du document Grist cree

        Raises:
            FileNotFoundError: Si le fichier n'existe pas
            GristConnectionError: Si le document cree ne contient aucune table
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Fichier introuvable : {file_path}")

        doc_id = self.api.upload_excel(file_path)

        tables = self.api.get_tables(doc_id)
        if not tables:
            raise GristConnectionError(
                f"Import echoue : aucune table trouvee dans le document '{doc_id}'. "
                "Verifiez que le fichier Excel contient au moins une feuille avec des donnees."
            )

        return doc_id
