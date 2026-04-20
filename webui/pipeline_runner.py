"""Run the full pipeline in a background thread, emitting SSE events."""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

from config import Settings
from core.data_analyzer import DataAnalyzer
from core.pipeline import PipelineOrchestrator
from core.grist_api import GristAPI
from core.grist_importer import GristImporter
from core.feature_engineer import FeatureEngineer
from core.archetype_engine import ArchetypeEngine
from webui.session import PipelineSession
from webui.checkpoint_handler import WebCheckpointHandler


def _emit(session: PipelineSession, event: str, data: str) -> None:
    session.event_queue.put((event, data))


def run_pipeline(session: PipelineSession, file_bytes: bytes, filename: str) -> None:
    """Entry point for the background thread."""
    settings = Settings()
    try:
        with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        _emit(session, "step", json.dumps({"message": "Analyse du fichier Excel…", "pct": 10}))
        analyzer = DataAnalyzer(settings)
        profile = analyzer.analyze(tmp_path)

        _emit(session, "step", json.dumps({"message": "Classification du domaine métier…", "pct": 25}))
        handler = WebCheckpointHandler(session)
        orchestrator = PipelineOrchestrator(settings, checkpoint_handler=handler)
        result = orchestrator.run(profile)

        if not result.dashboard_plan or not result.classification:
            session.error = "Pipeline incomplet — impossible de créer le document Grist."
            _emit(session, "error", json.dumps({"message": session.error}))
            return

        _emit(session, "step", json.dumps({"message": "Import du fichier dans Grist…", "pct": 65}))
        api = GristAPI(settings.GRIST_SERVER, settings.GRIST_API_KEY)
        importer = GristImporter(api)
        doc_id = importer.import_excel(tmp_path, summary_tables=profile.summary_tables)

        if result.feature_plan and result.feature_plan.features:
            _emit(session, "step", json.dumps({"message": "Application des colonnes dérivées…", "pct": 75}))
            fe = FeatureEngineer(settings)
            fe.apply(api, doc_id, result.feature_plan, result.classification.table_mapping)

        _emit(session, "step", json.dumps({"message": "Génération des pages du tableau de bord…", "pct": 85}))
        engine = ArchetypeEngine(api)
        created_pages = engine.apply(
            doc_id,
            result.classification,
            result.dashboard_plan,
            result.visual_intents,
        )

        doc_url = f"{settings.GRIST_SERVER}/doc/{doc_id}"
        session.result = {"doc_url": doc_url, "pages": created_pages}
        _emit(session, "complete", json.dumps({"doc_url": doc_url, "pages": created_pages}))

    except Exception as exc:
        session.error = str(exc)
        _emit(session, "error", json.dumps({"message": str(exc)}))


def start_pipeline_thread(session: PipelineSession, file_bytes: bytes, filename: str) -> None:
    t = threading.Thread(target=run_pipeline, args=(session, file_bytes, filename), daemon=True)
    t.start()
