#!/usr/bin/env python3
"""
Grist Excel Analyzer - CLI Interface

Analyse un document Grist existant (importé depuis Excel)
et utilise le LLM pour suggérer des formules, changements
de colonnes, et recommandations de widgets.

Usage:
    python main.py --doc-id {docId} --request "Dashboard de ventes"
    python main.py --doc-name "Mon Document" --request "Dashboard de ventes"
    python main.py --doc-name "Mon Document" --workspace "Home" --request "Dashboard de ventes" --dry-run
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

from core.grist_api import GristAPI, GristConnectionError, GristAuthError
from core.grist_analyzer import GristAnalyzer
from core.schema_analyzer import SchemaAnalyzer
from core.grist_updater import GristUpdater
from core.model_discovery import select_model
from config import Settings


def validate_doc_id(api: GristAPI, doc_id: str) -> bool:
    """Vérifier que le docId existe et est accessible."""
    try:
        api.get_tables(doc_id)
        return True
    except GristAuthError:
        print("❌ Erreur d'authentification. Vérifiez votre clé API Grist.")
        return False
    except Exception as e:
        print(f"❌ Impossible d'accéder au document '{doc_id}': {e}")
        print("   Vérifiez que le docId est correct et que vous avez les droits d'accès.")
        return False


def call_llm(
    messages: list,
    settings: Settings,
    model_name: str,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """Appeler le LLM via vLLM API.

    Args:
        messages: Messages conversationnels
        settings: Configuration
        model_name: Nom du modèle
        max_retries: Nombre maximal de retries

    Returns:
        JSON parsé de la réponse LLM

    Raises:
        ValueError: Si la réponse n'est pas un JSON valide
    """
    import requests
    import re

    vllm_url = f"{settings.VLLM_BASE_URL}/v1/chat/completions"

    for attempt in range(max_retries + 1):
        try:
            payload = {
                "model": model_name,
                "messages": messages,
                "max_tokens": 8192,
                "temperature": 0.3,
                "top_p": 0.9,
                "chat_template_kwargs": {"enable_thinking": False},
            }

            print(f"  ⏳ Appel LLM ({model_name})...")
            response = requests.post(
                vllm_url, json=payload, timeout=600
            )
            response.raise_for_status()
            result = response.json()

            # Extraire le contenu
            response_text = None
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                if "message" in choice:
                    content = choice["message"].get("content")
                    reasoning = choice["message"].get("reasoning")
                    if content:
                        response_text = content
                    elif reasoning:
                        response_text = reasoning

            if not response_text:
                raise ValueError("Aucun contenu dans la réponse LLM")

            # Extraire JSON du texte
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if not json_match:
                raise ValueError("Aucun JSON trouvé dans la réponse LLM")

            config = json.loads(json_match.group(0))
            return config

        except (requests.exceptions.RequestException, ValueError) as e:
            if attempt < max_retries:
                print(f"  ⚠️  Tentative {attempt + 1}/{max_retries + 1} échouée: {e}")
                print("  Nouvelle tentative...")
                continue
            raise ValueError(f"Échec après {max_retries + 1} tentatives: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyseur de documents Grist avec suggestions LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python main.py --doc-id abc123 --request "Dashboard de ventes"
  python main.py --doc-id abc123 --request "Améliorer le document" --dry-run
        """,
    )

    doc_group = parser.add_mutually_exclusive_group(required=True)
    doc_group.add_argument(
        "--doc-id", "-d", type=str,
        help="Identifiant du document Grist à analyser"
    )
    doc_group.add_argument(
        "--doc-name", "-n", type=str,
        help="Nom du document Grist (résolu automatiquement en docId)"
    )
    parser.add_argument(
        "--workspace", "-w", type=str, default=None,
        help="Limiter la recherche par nom à un workspace spécifique"
    )
    parser.add_argument(
        "--request", "-r", type=str, required=True,
        help="Description de ce que l'utilisateur veut réaliser"
    )
    parser.add_argument(
        "--output", "-o", type=str, default="./output/",
        help="Dossier de sortie (défaut: ./output/)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Afficher la config LLM sans l'appliquer"
    )
    parser.add_argument(
        "--model", "-m", type=str, default=None,
        help="Nom du modèle vLLM à utiliser"
    )

    args = parser.parse_args()

    # Configuration
    settings = Settings()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Résolution du modèle
    model_name = args.model or settings.VLLM_MODEL
    selected_model = select_model(settings, model_name=model_name)
    print(f"🤖 Modèle sélectionné: {selected_model}")

    # Initialisation API Grist
    grist_api = GristAPI(settings.GRIST_SERVER, settings.GRIST_API_KEY)

    # Résolution du docId (par nom ou directement)
    if args.doc_name:
        try:
            doc = grist_api.find_document(args.doc_name, workspace=args.workspace)
            doc_id = doc.id
            print(f"🔎 Document '{args.doc_name}' → {doc_id}")
        except GristConnectionError as e:
            print(f"❌ {e}")
            sys.exit(1)
    else:
        doc_id = args.doc_id

    # Étape 1: Valider le docId
    print(f"\n{'=' * 60}")
    print("ANALYSE DU DOCUMENT GRIST")
    print(f"{'=' * 60}")
    print(f"📄 Document: {doc_id}")
    print(f"📝 Request: {args.request}")

    if not validate_doc_id(grist_api, doc_id):
        sys.exit(1)

    # Étape 2: Analyser le document
    print(f"\n[1/4] 🔍 Analyse du document Grist...")
    analyzer = GristAnalyzer(grist_api)
    document_info = analyzer.analyze(doc_id)

    print(f"  ✓ {len(document_info.get_table_names())} table(s) trouvée(s)")
    for table_id in document_info.get_table_names():
        table = document_info.get_table(table_id)
        n_records = table.get("record_count", 0)
        n_columns = len(table.get("columns", []))
        print(f"    - {table['label']}: {n_columns} colonnes, {n_records} records")

    # Étape 3: Générer config via LLM
    print(f"\n[2/4] 🤖 Génération de la config LLM...")
    schema_analyzer = SchemaAnalyzer(document_info, args.request)
    messages = schema_analyzer.build_messages()

    try:
        config = call_llm(messages, settings, selected_model)
        print(f"  ✓ Config LLM générée")
    except ValueError as e:
        print(f"  ❌ Erreur LLM: {e}")
        sys.exit(1)

    # Sauvegarder la config JSON
    config_file = output_dir / "llm_config.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False, default=str)
    print(f"  ✓ Config sauvegardée: {config_file}")

    # Étape 4: Appliquer la config (ou dry-run)
    print(f"\n[3/4] 🔧 Application de la config...")

    if args.dry_run:
        print("\n  ⚠️  MODE SÉCURISÉ (dry-run) - Configuration affichée sans application")
        print(f"\n  Formules suggérées ({len(config.get('formulas', []))}):")
        for formula in config.get("formulas", []):
            print(f"    - {formula['table']}.{formula['column']}: {formula['formula']}")
        print(f"\n  Changements de colonnes ({len(config.get('columnChanges', []))}):")
        for change in config.get("columnChanges", []):
            print(f"    - {change['table']}.{change['column']}: {change['newType']}")
            if "choices" in change:
                print(f"      Choices: {change['choices']}")
    else:
        updater = GristUpdater(grist_api)
        summary = updater.apply_config(doc_id, config)
        print(f"  ✓ {summary['formulas_applied']} formule(s) appliquée(s)")
        print(f"  ✓ {summary['column_changes_applied']} changement(s) de colonne appliqué(s)")
        if summary["errors"]:
            print(f"  ⚠️  {len(summary['errors'])} erreur(s):")
            for err in summary["errors"]:
                print(f"    - {err}")

    # Afficher les recommandations
    print(f"\n[4/4] 📊 Recommandations de widgets/vues...")
    GristUpdater.print_recommendations(config)

    # Résumé
    print(f"\n{'=' * 60}")
    print("✅ TERMINÉ")
    print(f"{'=' * 60}")
    print(f"📁 Config: {config_file}")
    if not args.dry_run:
        print(f"🌐 Document Grist: {settings.GRIST_SERVER}/doc/{doc_id}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
