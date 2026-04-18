#!/usr/bin/env python3
"""Prompt Evaluation Tool — compares 5 system prompt variants per agent.

Usage:
    python eval_classifier.py --input samples/employees_rh.xlsx
    python eval_classifier.py --input samples/employees_rh.xlsx --agent insight_extractor
    python eval_classifier.py --input samples/employees_rh.xlsx --versions v1 v3

Output:
    output/prompt_eval/{agent}_{version}.json   ← raw output + metrics
    output/prompt_eval/report.md                ← comparative table
"""

import argparse
import json
import time
from pathlib import Path

from config import Settings
from core.data_analyzer import DataAnalyzer, DataProfile
from core.domain_classifier import DomainClassifier, ClassificationResult
from core.insight_extractor import InsightExtractor, InsightReport
from core.dashboard_composer import DashboardComposer, DashboardPlan

VALID_AGENTS = ["domain_classifier", "insight_extractor", "dashboard_composer"]
VALID_VERSIONS = ["v1", "v2", "v3", "v4", "v5"]


def load_prompt(agent: str, version: str) -> str:
    """Load a prompt variant from the prompts/ directory."""
    path = Path("prompts") / f"{agent}_{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def eval_domain_classifier(
    profile: DataProfile, system_prompt: str, settings: Settings
) -> dict:
    """Run DomainClassifier with a custom system prompt. Returns metrics dict."""
    classifier = DomainClassifier(settings)

    def classify_with_custom_prompt(p: DataProfile) -> ClassificationResult:
        prompt = classifier._build_prompt(p)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return ClassificationResult(**classifier._call_llm(messages))

    classifier.classify = classify_with_custom_prompt

    start = time.time()
    try:
        result = classifier.classify(profile)
        latency = time.time() - start
        return {
            "archetype": result.archetype,
            "confidence": result.confidence,
            "table_mapping": result.table_mapping,
            "params": result.params,
            "latency_s": round(latency, 2),
            "error": None,
        }
    except Exception as exc:
        return {
            "archetype": None,
            "confidence": None,
            "table_mapping": {},
            "params": {},
            "latency_s": round(time.time() - start, 2),
            "error": str(exc),
        }


def eval_insight_extractor(
    profile: DataProfile,
    classification: ClassificationResult,
    system_prompt: str,
    settings: Settings,
) -> dict:
    """Run InsightExtractor with a custom system prompt."""
    extractor = InsightExtractor(settings)

    def extract_with_custom_prompt(p, c):
        prompt = extractor._build_prompt(p, c)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return InsightReport(**extractor._call_llm(messages))

    extractor.extract = extract_with_custom_prompt

    start = time.time()
    try:
        result = extractor.extract(profile, classification)
        latency = time.time() - start
        return {
            "insight_count": len(result.insights),
            "insights": [i.model_dump() for i in result.insights],
            "latency_s": round(latency, 2),
            "error": None,
        }
    except Exception as exc:
        return {
            "insight_count": 0,
            "insights": [],
            "latency_s": round(time.time() - start, 2),
            "error": str(exc),
        }


def eval_dashboard_composer(
    classification: ClassificationResult,
    insights: InsightReport,
    system_prompt: str,
    settings: Settings,
) -> dict:
    """Run DashboardComposer with a custom system prompt."""
    composer = DashboardComposer(settings)

    def compose_with_custom_prompt(c, i):
        prompt = composer._build_prompt(c, i)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        raw_plan = DashboardPlan(**composer._call_llm(messages))
        return raw_plan.self_reflect(i)

    composer.compose = compose_with_custom_prompt

    start = time.time()
    try:
        result = composer.compose(classification, insights)
        latency = time.time() - start
        return {
            "page_count": len(result.pages),
            "section_count": sum(len(p.sections) for p in result.pages),
            "pages": result.model_dump(),
            "latency_s": round(latency, 2),
            "error": None,
        }
    except Exception as exc:
        return {
            "page_count": 0,
            "section_count": 0,
            "pages": {},
            "latency_s": round(time.time() - start, 2),
            "error": str(exc),
        }


def generate_report(results: dict, output_dir: Path) -> None:
    """Generate report.md comparing all agent/version combinations."""
    lines = ["# Prompt Evaluation Report\n"]

    for agent, versions in results.items():
        lines.append(f"## {agent}\n")
        if agent == "domain_classifier":
            lines.append("| Version | Archetype | Confidence | Latency (s) | Error |")
            lines.append("|---|---|---|---|---|")
            for v, r in versions.items():
                lines.append(
                    f"| {v} | {r.get('archetype','-')} | "
                    f"{r.get('confidence','-')} | {r.get('latency_s','-')} | "
                    f"{r.get('error') or '-'} |"
                )
        elif agent == "insight_extractor":
            lines.append("| Version | Insights | Latency (s) | Error |")
            lines.append("|---|---|---|---|---|")
            for v, r in versions.items():
                lines.append(
                    f"| {v} | {r.get('insight_count','-')} | "
                    f"{r.get('latency_s','-')} | {r.get('error') or '-'} |"
                )
        elif agent == "dashboard_composer":
            lines.append("| Version | Pages | Sections | Latency (s) | Error |")
            lines.append("|---|---|---|---|---|")
            for v, r in versions.items():
                lines.append(
                    f"| {v} | {r.get('page_count','-')} | "
                    f"{r.get('section_count','-')} | "
                    f"{r.get('latency_s','-')} | {r.get('error') or '-'} |"
                )
        lines.append("")

    report_path = output_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate prompt variants per LLM agent"
    )
    parser.add_argument("--input", required=True, help="Excel file path")
    parser.add_argument(
        "--agent", default="domain_classifier",
        choices=VALID_AGENTS,
        help="Agent to evaluate (default: domain_classifier)"
    )
    parser.add_argument(
        "--versions", nargs="+", default=VALID_VERSIONS,
        help="Versions to test (default: v1 v2 v3 v4 v5)"
    )
    parser.add_argument("--output", default="./output/", help="Output directory")
    args = parser.parse_args()

    settings = Settings()
    output_dir = Path(args.output) / "prompt_eval"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Analyzing {args.input}...")
    analyzer = DataAnalyzer(settings)
    profile = analyzer.analyze(args.input)
    print(f"  Sheets: {profile.sheets}")

    # Run domain_classifier first (needed as input for insight_extractor)
    classifier = DomainClassifier(settings)
    classification = classifier.classify(profile)

    insight_extractor = InsightExtractor(settings)
    insights = insight_extractor.extract(profile, classification)

    results: dict = {args.agent: {}}

    for version in args.versions:
        print(f"\nEvaluating {args.agent} {version}...")
        try:
            system_prompt = load_prompt(args.agent, version)
        except FileNotFoundError as e:
            print(f"  Skipping: {e}")
            continue

        if args.agent == "domain_classifier":
            r = eval_domain_classifier(profile, system_prompt, settings)
        elif args.agent == "insight_extractor":
            r = eval_insight_extractor(profile, classification, system_prompt, settings)
        elif args.agent == "dashboard_composer":
            r = eval_dashboard_composer(classification, insights, system_prompt, settings)
        else:
            continue

        results[args.agent][version] = r
        out_file = output_dir / f"{args.agent}_{version}.json"
        out_file.write_text(json.dumps(r, indent=2, ensure_ascii=False, default=str))
        print(f"  Saved: {out_file}")
        if r.get("error"):
            print(f"  Error: {r['error']}")

    generate_report(results, output_dir)


if __name__ == "__main__":
    main()
