"""Run the pipeline in a background thread, emitting SSE events."""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

from config import Settings
from core.data_analyzer import DataAnalyzer, DataProfile
from core.pipeline import PipelineOrchestrator
from core.grist_api import GristAPI
from core.grist_importer import GristImporter
from core.feature_engineer import FeatureEngineer
from core.archetype_engine import ArchetypeEngine
from core.insight_extractor import InsightEntry
from webui.session import PipelineSession
from webui.checkpoint_handler import WebCheckpointHandler


def _emit(session: PipelineSession, event: str, data: str) -> None:
    session.event_queue.put((event, data))


def _grist_steps(
    session: PipelineSession,
    result,
    tmp_path: str,
    profile: DataProfile,
    settings: Settings,
    intent: str,
) -> None:
    """Run Grist import + ArchetypeEngine, emit complete or error event."""
    try:
        _emit(session, "step", json.dumps({"message": "Import du fichier dans Grist…", "pct": 65}))
        api = GristAPI(settings.GRIST_SERVER, settings.GRIST_API_KEY)
        importer = GristImporter(api)
        doc_id = importer.import_excel(tmp_path, summary_tables=profile.summary_tables)

        features_applied = 0
        features_failed = 0
        if result.feature_plan and result.feature_plan.features:
            _emit(session, "step", json.dumps({"message": "Application des colonnes dérivées…", "pct": 75}))
            fe = FeatureEngineer(settings)
            applied, failed = fe.apply(api, doc_id, result.feature_plan, result.classification.table_mapping)
            features_applied = len(applied)
            features_failed = len(failed)

        _emit(session, "step", json.dumps({"message": "Génération des pages du tableau de bord…", "pct": 85}))
        engine = ArchetypeEngine(api)
        created_pages = engine.apply(
            doc_id,
            result.classification,
            result.dashboard_plan,
            result.visual_intents,
        )

        doc_url = f"{settings.GRIST_SERVER}/doc/{doc_id}"
        insights_used = [ins.finding for ins in (result.insights.insights if result.insights else [])]

        complete_payload = {
            "doc_url": doc_url,
            "pages": created_pages,
            "intent_used": intent,
            "insights_used": insights_used,
            "features_applied": features_applied,
            "features_failed": features_failed,
            "archetype": result.classification.archetype if result.classification else "",
            "confidence": result.classification.confidence if result.classification else 0.0,
        }
        session.result = complete_payload
        _emit(session, "complete", json.dumps(complete_payload))

    except Exception as exc:
        session.error = str(exc)
        _emit(session, "error", json.dumps({"message": str(exc)}))


def run_pipeline(session: PipelineSession, file_bytes: bytes, filename: str) -> None:
    """Full pipeline run (Phase 1 + Phase 2)."""
    settings = Settings()
    try:
        with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        session.cached_tmp_path = tmp_path

        _emit(session, "step", json.dumps({"message": "Analyse du fichier Excel…", "pct": 10}))
        analyzer = DataAnalyzer(settings)
        profile = analyzer.analyze(tmp_path)

        _emit(session, "step", json.dumps({"message": "Classification du domaine métier…", "pct": 25}))
        handler = WebCheckpointHandler(session)
        orchestrator = PipelineOrchestrator(settings, checkpoint_handler=handler)
        result = orchestrator.run(profile)

        # Cache Phase 1 outputs for potential refinement
        session.cached_profile = profile
        session.cached_classification = result.classification

        if not result.dashboard_plan or not result.classification:
            session.error = "Pipeline incomplet — impossible de créer le document Grist."
            _emit(session, "error", json.dumps({"message": session.error}))
            return

        intent = ""
        if session.checkpoint1_response:
            intent = session.checkpoint1_response.get("user_intent", "")

        _grist_steps(session, result, tmp_path, profile, settings, intent)

    except Exception as exc:
        session.error = str(exc)
        _emit(session, "error", json.dumps({"message": str(exc)}))


def run_refinement(
    session: PipelineSession,
    intent: str,
    selected_insights: list[InsightEntry],
) -> None:
    """Phase 2 re-run using cached Phase 1 data."""
    settings = Settings()
    try:
        profile = session.cached_profile
        classification = session.cached_classification
        if profile is None or classification is None:
            _emit(session, "error", json.dumps({"message": "Données d'analyse manquantes — veuillez recommencer."}))
            return

        _emit(session, "step", json.dumps({"message": "Application du nouveau filtre de colonnes…", "pct": 40}))
        orchestrator = PipelineOrchestrator(settings)
        result = orchestrator.run_from_insights(
            cached_profile=profile,
            cached_classification=classification,
            selected_insights=selected_insights,
            intent=intent,
        )

        if not result.dashboard_plan or not result.classification:
            session.error = "Affinement incomplet — impossible de créer le document Grist."
            _emit(session, "error", json.dumps({"message": session.error}))
            return

        tmp_path = session.cached_tmp_path
        if tmp_path is None:
            _emit(session, "error", json.dumps({"message": "Fichier source non disponible pour l'affinement."}))
            return

        _grist_steps(session, result, tmp_path, profile, settings, intent)

    except Exception as exc:
        session.error = str(exc)
        _emit(session, "error", json.dumps({"message": str(exc)}))


def start_pipeline_thread(session: PipelineSession, file_bytes: bytes, filename: str) -> None:
    t = threading.Thread(target=run_pipeline, args=(session, file_bytes, filename), daemon=True)
    t.start()


def start_refinement_thread(
    session: PipelineSession,
    intent: str,
    selected_insights: list[InsightEntry],
) -> None:
    t = threading.Thread(target=run_refinement, args=(session, intent, selected_insights), daemon=True)
    t.start()
