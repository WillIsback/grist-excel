#!/usr/bin/env python3
"""Data-to-Dashboard — CLI Interface

A non-expert user provides an Excel file.
The tool produces a fully configured Grist document with pages,
charts, card views, and forms — driven by business insights.

Usage:
    python main.py --input employees_rh.xlsx
    python main.py --input sales_2024.xlsx --dry-run
    python main.py --input data.xlsx --output ./results/
"""

import warnings
warnings.filterwarnings('ignore')

import argparse
import json
import sys
from pathlib import Path

from config import Settings
from core.grist_api import GristAPI
from core.grist_importer import GristImporter
from core.data_analyzer import DataAnalyzer
from core.pipeline import PipelineOrchestrator
from core.archetype_engine import ArchetypeEngine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Data-to-Dashboard: Excel -> Grist document with dashboards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input", "-i", type=str, required=True,
        help="Chemin vers le fichier Excel (.xlsx)"
    )
    parser.add_argument(
        "--output", "-o", type=str, default="./output/",
        help="Dossier de sortie pour les logs JSON (défaut: ./output/)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Afficher le DashboardPlan JSON sans créer de document Grist"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Afficher la sortie JSON de chaque étape du pipeline"
    )

    args = parser.parse_args()
    settings = Settings()
    if args.debug:
        settings.DEBUG = True
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'=' * 60}")
    print("DATA-TO-DASHBOARD")
    print(f"{'=' * 60}")
    print(f"Fichier : {args.input}")

    # Step 1: Analyze the Excel file
    print("\n[1/4] Analyse du fichier Excel...")
    analyzer = DataAnalyzer(settings)
    try:
        profile = analyzer.analyze(args.input)
    except FileNotFoundError:
        print(f"Fichier introuvable : {args.input}")
        sys.exit(1)
    print(f"  {len(profile.sheets)} feuille(s) : {profile.sheets}")
    if profile.summary_tables:
        print(f"  Syntheses : {len(profile.summary_tables)} table(s)")

    # Step 2: Run LLM pipeline
    print("\n[2/4] Pipeline LLM (classification + insights + dashboard plan)...")
    orchestrator = PipelineOrchestrator(settings)
    result = orchestrator.run(profile)

    if result.errors:
        print(f"  Avertissements pipeline :")
        for err in result.errors:
            print(f"    - {err}")

    if result.classification:
        print(f"  Archetype : {result.classification.archetype} "
              f"(confiance : {result.classification.confidence:.0%})")
    if result.insights:
        print(f"  Insights  : {len(result.insights.insights)}")
    if result.dashboard_plan:
        print(f"  Pages     : {len(result.dashboard_plan.pages)}")

    # Save pipeline result
    result_file = output_dir / "pipeline_result.json"
    result.save(str(result_file))
    print(f"  Pipeline result sauvegardé : {result_file}")

    # Dry-run: print plan and exit
    if args.dry_run:
        print("\n[DRY-RUN] DashboardPlan JSON :")
        if result.dashboard_plan:
            print(json.dumps(result.dashboard_plan.model_dump(), indent=2, ensure_ascii=False))
        else:
            print("  (pas de DashboardPlan — pipeline incomplet)")
        print("\nDRY-RUN terminé. Aucun document Grist créé.")
        return

    if not result.dashboard_plan or not result.classification:
        print("\nPipeline incomplet — impossible de créer le document Grist.")
        sys.exit(1)

    # Step 3: Import Excel to Grist
    print("\n[3/4] Import du fichier Excel dans Grist...")
    api = GristAPI(settings.GRIST_SERVER, settings.GRIST_API_KEY)
    importer = GristImporter(api)
    try:
        doc_id = importer.import_excel(args.input, summary_tables=profile.summary_tables)
    except KeyboardInterrupt:
        raise
    except SystemExit:
        raise
    except Exception as exc:
        print(f"  Erreur import : {exc}")
        sys.exit(1)
    print(f"  Document créé : {doc_id}")

    if settings.DEBUG:
        from core.debug_utils import debug_print
        debug_print("GristImporter", {"doc_id": doc_id}, True)

    # Step 3b: Apply engineered formula columns
    if result.feature_plan and result.feature_plan.features:
        print("\n[3b/4] Application des colonnes dérivées...")
        from core.feature_engineer import FeatureEngineer
        fe = FeatureEngineer(settings)
        applied, failed = fe.apply(api, doc_id, result.feature_plan, result.classification.table_mapping)
        print(f"  Colonnes appliquées : {applied}")
        if failed:
            print(f"  Colonnes échouées  : {failed}")
        if settings.DEBUG:
            from core.debug_utils import debug_print
            debug_print("FeatureEngineer.apply", {"applied": applied, "failed": failed}, True)

    # Step 4: Apply archetype template
    print("\n[4/4] Application du template archetype...")
    engine = ArchetypeEngine(api)
    created_pages = engine.apply(
        doc_id,
        result.classification,
        result.dashboard_plan,
        result.visual_intents,
    )
    print(f"  Pages créées : {created_pages}")

    print(f"\n{'=' * 60}")
    print("TERMINÉ")
    print(f"{'=' * 60}")
    print(f"Document Grist : {settings.GRIST_SERVER}/doc/{doc_id}")
    print(f"Pipeline log   : {result_file}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
