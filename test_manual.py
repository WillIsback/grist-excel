#!/usr/bin/env python3
"""Manual test runner for Plan A: Foundation pipeline.

Walks through each step and prints results for visual inspection/debugging.

Usage:
    python test_manual.py [--upload] [--analyze] [--import] [--all]

Steps:
    1. Upload Excel → Grist (creates document with tables)
    2. Analyze Excel → DataProfile (markdown + stats + FK detection)
    3. Full import via GristImporter (upload + verify)
"""

import argparse
import json
import sys
from pathlib import Path

from core.grist_api import GristAPI, GristConnectionError, GristAuthError
from core.data_analyzer import DataAnalyzer
from core.grist_importer import GristImporter
from config import settings

SAMPLE_FILES = [
    "samples/employees_rh.xlsx",
    "samples/demo_data.xlsx",
    "samples/sample_employees.xlsx",
]


def print_header(title: str):
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def print_section(title: str):
    print(f"\n--- {title} ---")


def step1_list_documents(api: GristAPI):
    """List existing documents."""
    print_section("Existing documents")
    docs = api.list_documents()
    if not docs:
        print("  (no documents found)")
        return
    for doc in docs:
        print(f"  - {doc.id}: \"{doc.name}\" (workspace: {doc.workspace_name})")


def step2_upload_excel(api: GristAPI, file_path: str):
    """Upload an Excel file to Grist and show the result."""
    print_section(f"Uploading: {file_path}")

    if not Path(file_path).exists():
        print(f"  FILE NOT FOUND: {file_path}")
        return None

    try:
        doc_id = api.upload_excel(file_path)
        print(f"  SUCCESS: Document created with docId = {doc_id}")

        # Show tables created
        tables = api.get_tables(doc_id)
        print_section(f"Tables in {doc_id}")
        if not tables:
            print("  (no tables found)")
        for t in tables:
            print(f"  - Table: {t['id']}")
            # Show columns
            cols = api.get_columns(doc_id, t["id"])
            for c in cols:
                ctype = c.get("fields", {}).get("type", "?")
                clabel = c.get("fields", {}).get("label", c["id"])
                print(f"      Column: {c['id']} ({ctype}) label=\"{clabel}\"")
            # Show record count
            records = api.get_records(doc_id, t["id"], limit=5)
            print(f"      Records: {len(records)} (showing first 5)")
            for r in records:
                rid = r.get("cells", {})
                print(f"        {rid}")

        return doc_id

    except GristAuthError:
        print("  ERROR: Authentication failed. Check GRIST_API_KEY.")
        return None
    except GristConnectionError as e:
        print(f"  ERROR: {e}")
        return None
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        return None


def step3_analyze_excel(file_path: str):
    """Analyze Excel file locally and show DataProfile."""
    print_section(f"Analyzing: {file_path}")

    if not Path(file_path).exists():
        print(f"  FILE NOT FOUND: {file_path}")
        return

    analyzer = DataAnalyzer()
    profile = analyzer.analyze(file_path)

    # Sheets
    print_section("Sheets")
    for s in profile.sheets:
        cols = profile.columns[s]
        print(f"  - {s}: {cols}")

    # Stats
    print_section("Column Statistics")
    for key, stat in profile.stats.items():
        print(f"  {key}:")
        for k, v in stat.items():
            print(f"    {k}: {v}")

    # FK detection
    print_section("Apparent Foreign Keys")
    if not profile.apparent_fk:
        print("  (none detected)")
    for fk in profile.apparent_fk:
        print(f"  {fk['from']} -> {fk['to']}")

    # Markdown summary
    print_section("Markdown Summary (first 1000 chars)")
    print(profile.markdown_summary[:1000])

    # Prompt context
    print_section("Prompt Context Output")
    print(profile.as_prompt_context())


def step4_full_import(api: GristAPI, file_path: str):
    """Use GristImporter for full upload + verify."""
    print_section(f"Full Import via GristImporter: {file_path}")

    if not Path(file_path).exists():
        print(f"  FILE NOT FOUND: {file_path}")
        return None

    importer = GristImporter(api)
    try:
        doc_id = importer.import_excel(file_path)
        print(f"  SUCCESS: Imported to docId = {doc_id}")

        tables = api.get_tables(doc_id)
        print(f"  Verified {len(tables)} table(s): {[t['id'] for t in tables]}")
        return doc_id
    except GristConnectionError as e:
        print(f"  IMPORT FAILED: {e}")
        return None
    except FileNotFoundError as e:
        print(f"  FILE NOT FOUND: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Manual test runner for Plan A pipeline")
    parser.add_argument(
        "--file", "-f", type=str, default=SAMPLE_FILES[0],
        help=f"Excel file to test (default: {SAMPLE_FILES[0]})"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--upload", action="store_true", help="Step 2: Upload Excel to Grist")
    group.add_argument("--analyze", action="store_true", help="Step 3: Analyze Excel locally")
    group.add_argument("--import", dest="do_import", action="store_true", help="Step 4: Full import")
    group.add_argument("--list", action="store_true", help="List existing documents")
    group.add_argument("--all", action="store_true", help="Run all steps")
    args = parser.parse_args()

    file_path = args.file
    if not Path(file_path).is_absolute():
        file_path = Path(__file__).parent / file_path

    # Init API
    api = GristAPI(settings.GRIST_SERVER, settings.GRIST_API_KEY)

    try:
        connected = api.test_connection()
        print_header("Grist Connected")
        print(f"  Server: {settings.GRIST_SERVER}")
        print(f"  Status: {'OK' if connected else 'FAILED'}")
    except Exception as e:
        print_header("Grist Connection Failed")
        print(f"  ERROR: {e}")
        print("  Start Grist with: ./start-grist.sh")
        sys.exit(1)

    if args.all or args.list:
        step1_list_documents(api)

    if args.all or args.upload:
        doc_id = step2_upload_excel(api, str(file_path))

    if args.all or args.analyze:
        step3_analyze_excel(str(file_path))

    if args.all or args.do_import:
        doc_id = step4_full_import(api, str(file_path))

    print_header("DONE")


if __name__ == "__main__":
    main()
