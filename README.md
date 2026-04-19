# Grist Excel to Application Converter

Automatically transforms Excel files into fully configured Grist applications with dashboards, forms, and charts — powered by local LLM inference.

## Overview

Upload an Excel spreadsheet and receive a ready-to-use Grist document with:

- **Smart schema inference** — column types, relationships, and constraints
- **Business insight extraction** — anomalies, distributions, correlations
- **Dashboard generation** — archetype-aware layouts (HR, analytics, project management, etc.)
- **Interactive widgets** — charts, card views, forms, calendars

```bash
python main.py --input employees_rh.xlsx
python main.py --input sales_2024.xlsx --dry-run
python main.py --input data.xlsx --output ./results/
```

## Architecture

```
Excel File
    │
    ▼
[Data Analyzer]     Parse sheets, infer types, extract samples
    │
    ▼
[Domain Classifier] Match to archetype (HR, finance, project, …)
    │
    ▼
[Insight Extractor] Statistical analysis + LLM-powered insights
    │
    ▼
[Dashboard Composer] Generate page/widget plan
    │
    ▼
[Grist Importer]    Upload raw data to Grist via API
    │
    ▼
[Archetype Engine]  Apply template widgets, charts, forms
    │
    ▼
Grist Document
```

### LLM Backend

Uses a local vLLM instance (e.g. `Qwen3.6-35B-A3B-FP8`) for all inference. No external API calls — fully self-hosted.

## Setup

### Prerequisites

- Python 3.11+
- Local vLLM server running (default: `http://172.17.0.1:30000`)
- Grist instance running (default: `http://localhost:8484`)

### Installation

```bash
cd grist-excel
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### Configuration

Copy the example env file and adjust values:

```bash
cp .env.example .env   # if provided, otherwise create manually
```

Required environment variables:

| Variable | Default | Description |
|---|---|---|
| `VLLM_BASE_URL` | `http://172.17.0.1:30000` | Local vLLM inference endpoint |
| `VLLM_MODEL` | `Qwen/Qwen3.6-35B-A3B-FP8` | Model identifier |
| `GRIST_SERVER` | `http://localhost:8484` | Grist instance URL |
| `GRIST_API_KEY` | *(empty)* | Grist API key from Profile Settings |
| `GRIST_DOC_ID` | *(empty)* | Target document ID |

## Usage

### Basic pipeline

```bash
python main.py --input samples/demo_data.xlsx
```

### Dry run (no Grist creation)

```bash
python main.py --input samples/demo_data.xlsx --dry-run
```

Outputs the dashboard plan as JSON without touching Grist.

### Debug mode

```bash
python main.py --input samples/demo_data.xlsx --debug
```

Prints JSON output from each pipeline agent step.

### Custom output directory

```bash
python main.py --input data.xlsx --output ./results/
```

## Project Structure

```
grist-excel/
├── main.py                  # CLI entry point
├── config.py                # Settings (pydantic, env-based)
├── requirements.txt
├── .env                     # ← NEVER commit (contains API keys)
│
├── core/                    # Pipeline stages
│   ├── data_analyzer.py
│   ├── domain_classifier.py
│   ├── insight_extractor.py
│   ├── dashboard_composer.py
│   ├── grist_api.py
│   ├── grist_importer.py
│   ├── archetype_engine.py
│   └── pipeline.py
│
├── archetypes/              # Domain-specific templates
│   ├── base.py
│   ├── hr.py
│   ├── decisionnel.py
│   ├── project.py
│   ├── student.py
│   ├── si.py
│   └── support.py
│
├── prompts/                 # LLM prompt templates (versioned)
│   ├── domain_classifier_v*.md
│   ├── data_analyzer_v*.md
│   ├── insight_extractor_v*.md
│   └── dashboard_composer_v*.md
│
├── templates/widgets/       # Grist widget JSON templates
├── samples/                 # Demo files (gitignored)
├── tests/                   # pytest suite
├── output/                  # Generated artifacts (gitignored)
└── docs/
```

## Archetypes

The domain classifier maps input data to one of several archetypes, each with pre-built widget templates:

| Archetype | Description | Typical Widgets |
|---|---|---|
| `hr` | Employee/HR data | Org chart, headcount cards, leave tracker |
| `decisionnel` | Business intelligence | KPI dashboards, trend charts |
| `project` | Project management | Gantt views, task boards |
| `student` | Academic data | Grade trackers, schedules |
| `si` | IT/service desk | Ticket queues, SLA monitors |
| `support` | Customer support | Ticket views, satisfaction scores |
| `generic` | Fallback | Basic table + summary |

## Security Notes

- **Never commit `.env`** — it contains your Grist API key
- **Never commit `output/`** — contains generated `.grist` documents and credential files
- **Sample Excel files are gitignored** — they may contain sensitive personnel data
- All LLM inference runs locally via vLLM — no data leaves your machine

## Development

### Running tests

```bash
uv pip install -r requirements.txt
pytest
```

### Adding a new archetype

1. Create `archetypes/my_domain.py` inheriting from `BaseArchetype`
2. Register it in `archetypes/__init__.py`
3. Add prompt templates in `prompts/`
4. Add widget templates in `templates/widgets/`

## License

Private / Internal use.
