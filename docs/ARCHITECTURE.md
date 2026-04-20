# grist-excel — Documentation Architecture

## 1. Principes Fondamentaux

### 1.1 Pipeline Multi-Agents Déterministe

Le système suit un pipeline séquentiel en 6 agents, où chaque
étape produit un artefact structuré consommé par le suivant.
Chaque agent est isolé, testable indépendamment, et peut
échouer sans faire tomber le pipeline (erreurs accumulées).

### 1.2 Séparation stricte LLM / Règles

- **LLM** (vLLM local, Qwen3.6-35B): classification, insights,
  dashboard plan, features — tout ce qui nécessite du raisonnement
- **Règles déterministes**: visual intents, validation Reflexion,
  import Excel, résolution de tables — tout ce qui peut être
  vérifié statiquement

### 1.3 Guided JSON Schema

Tous les appels LLM utilisent `guided_json` avec des schémas
Pydantic stricts. Température fixée à 0.2-0.3. Retry automatique
en cas de JSON invalide (prompt plus strict).

### 1.4 Archétypes Extensibles

Le système supporte 7 archétypes métier (HR, DECISIONNEL,
SUPPORT, STUDENT, SI, PROJECT, GENERIC). Chacun implémente
l'interface `BaseArchetype`. Nouveau archétype = nouveau fichier
dans `archetypes/`.

### 1.5 Widgets Officiels Grist en Premium

Advanced Charts, Map, Markdown sont matérialisés via
sections custom avec `options.customView` sérialisé en JSON.
La sélection se fait via `VisualIntentResolver` (règles, pas LLM).

### 1.6 Zéro Cloud

Tout tourne localement: vLLM, Grist, Python. Aucune API externe
d'inférence requise.

---

## 2. Architecture du Pipeline

```
  Excel File
      |
      v
  [Agent 1: DataAnalyzer]         -> DataProfile
      |  - markitdown -> markdown summary
      |  - pandas  -> stats par colonne
      |  - heuristiques -> apparent FKs
      |  - scoring -> summary tables (cat x numeric)
      v
  [Agent 2: DomainClassifier]     -> ClassificationResult
      |  - LLM guided_json
      |  - 7 archétypes possibles
      |  - fallback GENERIC si confidence < 0.6
      v
  [Agent 3: InsightExtractor]     -> InsightReport
      |  - LLM guided_json
      |  - Max 5 insights (distribution, trend, outlier,
      |    relation, kpi)
      v
  [Agent 3.5: FeatureEngineer]    -> FeaturePlan
      |  - LLM guided_json
      |  - Génère colonnes dérivées Grist (formules Python)
      |  - Max 6 features
      |  - Phase 1: plan() -> phase 2: apply() sur Grist live
      v
  [VisualIntentResolver]          -> VisualIntentPlan
      |  - 100% règles déterministes (pas de LLM)
      |  - 5 kinds: trend, cross_tab, geo, narrative,
      |    entity_detail
      |  - Promote un widget premium (advanced_chart, map,
      |    markdown) selon scoring pondéré
      v
  [Agent 4: DashboardComposer]    -> DashboardPlan
      |  - LLM guided_json
      |  - Mappe insights -> widgets chart
      |  - Append page "Syntheses croisees" (cross_tabs)
      |  - Auto-filter charts invalides (line sans x/y)
      v
  [Agent 4.5: ReflexionValidator] -> DashboardPlan validé
      |  - Vérifie chaque col x/y existe dans les données
      |  - Drop sections invalides
      |  - Si >50% drop -> retry LLM une fois avec contexte
      v
  [GristImporter]                 -> Grist Document
      |  - Upload Excel -> docId
      |  - Crée tables + colonnes + records
      |  - Importe summary tables
      |  - Applique colonnes dérivées (FeatureEngineer.apply)
      |  - Masque raw pages des summary tables
      v
  [ArchetypeEngine]               -> Grist Document complet
      |  - Dispatche vers l'archétype correspondant
      |  - Crée pages, sections (table, chart, card_list,
      |    form, custom widget)
      |  - Résout tableId -> tableRef (accent-insensitive)
      |  - Matérialise widgets officiels (advanced_chart,
      |    map, markdown)
      v
  Grist Document (fini)
```

---

## 3. Structure du Projet

```
grist-excel/
├── main.py                     # Entry point CLI (4 étapes)
├── config.py                   # Settings pydantic (env + .env)
├── pyproject.toml              # Dépendances + config
├── requirements.txt            # Pip dependencies
├── pyrightconfig.json          # Type checking
├── pytest.ini                  # Test config
│
├── core/
│   ├── pipeline.py             # PipelineOrchestrator + PipelineResult
│   ├── data_analyzer.py        # Agent 1: Excel -> DataProfile
│   ├── domain_classifier.py    # Agent 2: DataProfile -> Classification
│   ├── insight_extractor.py    # Agent 3: Classification -> Insights
│   ├── feature_engineer.py     # Agent 3.5: Features Grist
│   ├── visual_intents.py       # VisualIntentResolver (rules-based)
│   ├── dashboard_composer.py   # Agent 4: DashboardPlan
│   ├── reflexion.py            # Agent 4.5: Validation + retry
│   ├── grist_api.py            # Client API REST Grist complet
│   ├── grist_importer.py       # Excel -> Grist import
│   ├── archetype_engine.py     # Dispatcher archetype
│   └── debug_utils.py          # Debug print helpers
│
├── archetypes/
│   ├── base.py                 # BaseArchetype + GristTableResolver
│   │                         + helpers (sections, widgets officiels)
│   ├── generic.py              # Template générique
│   ├── hr.py                   # Ressources Humaines
│   ├── decisionnel.py          # Aide à la décision
│   ├── support.py              # Support / tickets
│   ├── student.py              # Données étudiants
│   ├── si.py                   # Système d'information
│   └── project.py              # Gestion de projet
│
├── prompts/                    # Prompts LLM versionnés (v1-v5)
│   ├── data_analyzer_v*.md
│   ├── domain_classifier_v*.md
│   ├── insight_extractor_v*.md
│   └── dashboard_composer_v*.md
│
├── templates/widgets/          # Templates JSON widgets Grist
│   ├── chart.json
│   ├── table.json
│   └── form.json
│
├── samples/                    # Données de test
│   ├── sample_employees.xlsx
│   ├── employees_rh.xlsx
│   ├── demo_data.xlsx
│   └── sites_geo_validation.xlsx
│
├── tests/                      # Tests pytest
│   ├── conftest.py
│   ├── test_pipeline.py
│   ├── test_data_analyzer.py
│   ├── test_domain_classifier.py
│   ├── test_insight_extractor.py
│   ├── test_feature_engineer.py
│   ├── test_visual_intents.py
│   ├── test_dashboard_composer.py
│   ├── test_grist_api.py
│   ├── test_grist_importer.py
│   ├── test_archetype_engine.py
│   ├── test_archetype_base.py
│   ├── test_base_archetype.py
│   ├── test_reflexion.py
│   ├── test_webui_session.py
│   ├── test_webui_server.py
│   └── test_new_main.py
│
├── webui/                      # Interface web FastAPI + SSE
│   ├── server.py               # FastAPI app, routes upload/stream/checkpoints/refine
│   ├── session.py              # SessionStore + PipelineSession (thread-safe, en mémoire)
│   ├── checkpoint_handler.py   # WebCheckpointHandler (bloque pipeline sur threading.Event)
│   ├── pipeline_runner.py      # run_pipeline(), run_refinement(), start_*_thread()
│   ├── templates/
│   │   ├── index.html          # Page upload
│   │   └── run.html            # Page pipeline (progress, checkpoints, résultat, affinement)
│   └── static/
│       ├── style.css           # Styles UI (Grist-inspired)
│       └── app.js              # Client vanilla JS (SSE, écrans, formulaires, affinement)
│
├── web.py                      # Entry point uvicorn (uv run python web.py)
├── start-webui.sh              # Script de démarrage Web UI
├── start-grist.sh              # Script de démarrage Grist (Docker)
│
├── docs/                       # Documentation projet
│   ├── superpowers/
│   │   ├── plans/              # Plans de développement
│   │   └── specs/              # Specs architecturales
│   ├── visual-intents-and-official-widgets.md
│   ├── grist-actions-validated.md
│   └── ARCHITECTURE.md         # Ce fichier
├── .design/
│   └── api-rest-design.md
├── output/                     # Résultats pipeline (JSON)
├── .env                        # Secrets (NON versionné)
└── README.md
```

---

## 4. Composants Clés — Détails

### 4.1 DataAnalyzer (Agent 1)

**Entrée:** fichier .xlsx
**Sortie:** `DataProfile` (dataclass)

**Fonctions:**

- `markitdown`: conversion Excel -> Markdown pour LLM
- `pandas`: stats par colonne (null, unique, min/max/avg ou top values)
- Heuristique FK: `ID_X` -> cherche sheet X, colonnes communes
- Summary Tables: scoring cat x numeric pairs, top 4 retenus

**Scoring summary tables:**

```
score = coverage*10 + group_balance + metric_keywords +
        category_keywords + group_count_bonus
```

**Méthodes:**

- `DataProfile.as_prompt_context()` -> texte pour injection prompt
- `DataProfile.to_json()` -> JSON pour guided_json

---

### 4.2 DomainClassifier (Agent 2)

**Entrée:** `DataProfile`
**Sortie:** `ClassificationResult` (Pydantic)

**Schéma JSON guidé:**

- `archetype`: HR | DECISIONNEL | SUPPORT | STUDENT | SI | PROJECT | GENERIC
- `confidence`: 0.0-1.0
- `table_mapping`: `{role_semantique: nom_feuille_exact}`
- `params`: `{param_name: col_name_exact}`

**Règle métier:** `confidence < 0.6` -> forcée en GENERIC

---

### 4.3 InsightExtractor (Agent 3)

**Entrée:** `DataProfile` + `ClassificationResult`
**Sortie:** `InsightReport` (Pydantic)

**Types:** distribution, trend, outlier, relation, kpi
**Max 5 insights**, triés par priority (1=plus important)

**Prompt injecte:** archetype, table_mapping, profile JSON,
angles d'analyse attendus

---

### 4.4 FeatureEngineer (Agent 3.5)

**Entrée:** `DataProfile` + `Classification` + `Insights`
**Sortie:** `FeaturePlan` (Pydantic)

**Deux phases:**

1. `plan()`: LLM génère `FormulaColumn[]` (max 6)
   Chaque formula utilise syntaxe Grist Python (`$ColName`,
   `Table.lookupRecords()`, `TODAY()`, etc.)
2. `apply()`: PATCH API Grist pour créer les colonnes
   Retourne `(applied[], failed[])` — continue malgré erreurs

---

### 4.5 VisualIntentResolver (Rules-Based)

**Entrée:** `DataProfile` + `Classification` + `Insights`
**Sortie:** `VisualIntentPlan` (Pydantic)

**5 types d'intents:**

1. **cross_tab**: depuis summary_tables, score basé sur insights matching
2. **trend**: depuis insights de type "trend"
3. **geo**: détection colonnes lat/lon par keywords + stats
4. **narrative**: top 2 insights -> markdown block
5. **entity_detail**: table principale -> card_list

**Scoring promotion premium:**

```
score = priority*0.7 + confidence*0.3 + kind_bonus + presentation_bonus

kind_bonus: trend=0.08, cross_tab=0.06, geo=0.05, narrative=0.04, entity_detail=0.02
presentation_bonus: hero_chart=0.10, secondary=0.05, summary_page=0.04, geo_page=0.04, narrative_block=0.03, detail_page=0.01
```

---

### 4.6 DashboardComposer (Agent 4)

**Entrée:** `Classification` + `Insights` + `FeaturePlan` + `VisualIntents`
**Sortie:** `DashboardPlan` (Pydantic)

**Pages générées:**

1. Dashboard principal (charts basés sur insights)
2. Page cards (table principale)
3. Page form (table principale)
4. - "Syntheses croisees" (append cross_tabs ou summary_tables)

**Règles de validation inline:**

- chart sans `chart_type` -> drop
- line chart sans `x`+`y` -> drop
- `self_reflect()`: drop widgets non justifiés par insights

**Prompt injecte:** mapping, colonnes typées (N/T), règles charts,
insights, features, summary tables, visual intents, retry context

---

### 4.7 ReflexionValidator (Agent 4.5)

**Entrée:** `DashboardPlan` + `raw_cols` + `engineered_cols`
**Sortie:** `DashboardPlan` validé

**Validation déterministe:**

- `_normalize()`: NFKD -> ASCII -> lowercase
- Vérifie chaque col x/y existe dans raw+engineered
- Drop sections invalides, pages vides supprimées

**Retry strategy:**

- Si `drop_ratio <= 50%` -> retour cleaned
- Si `drop_ratio > 50%` -> retry LLM une fois avec:
  `dropped_sections` + `available_columns`

---

### 4.8 ArchetypeEngine + BaseArchetype

**Dispatcher** vers l'archétype correct.

**BaseArchetype fournit des helpers communs:**

- `_create_page()`: AddRecord sur `_grist_Views` + TabBar + Pages
- `_get_col_ref_map()`: `{colId: colRef}` pour une table
- `_add_table_section()`: grid section
- `_add_chart_section()`: chart section avec résolution x/y
- `_add_card_list_section()`: detail section
- `_add_form_section()`: form section
- `_add_custom_widget_section()`: customView JSON imbriqué
- `_add_geo_widget_page()`: page dédiée widget Map
- `_add_markdown_widget_page()`: page dédiée widget Markdown
- `_materialize_additional_visual_widgets()`: map + markdown pages

**GristTableResolver:** tableId -> tableRef (accent-insensitive)

**Widgets officiels:**

| Widget | ID |
|--------|-----|
| advanced_chart | `@gristlabs/widget-chart` |
| markdown | `@gristlabs/widget-markdown` |
| map | `@gristlabs/widget-map#map` |
| jupyterlite | `@gristlabs/widget-jupyterlite` |

---

### 4.9 GristAPI

Client REST complet avec:

- Découverte auto org/workspace
- Retry exponentiel (3 tentatives)
- CRUD: docs, tables, columns, records
- `apply_actions`: actions internes Grist
- Widget discovery: `GET /api/widgets`, cache

**Routes utilisées:**

```
POST /api/docs                          (upload Excel ou doc vide)
POST /api/docs/{id}/tables              (créer table)
POST /api/docs/{id}/tables/{tid}/columns (créer colonnes)
POST /api/docs/{id}/tables/{tid}/records (ajouter records)
POST /api/docs/{id}/apply               (actions internes)
GET  /api/docs/{id}/tables/{tid}        (lire table)
GET  /api/widgets                       (découvrir widgets)
```

---

### 4.10 GristImporter

Import Excel -> Grist:

1. Crée doc vide -> supprime `Table1` auto-créé
2. Pour chaque sheet: `_safe_table_id` + `_safe_col_id`
   (normalisation accents -> ASCII)
3. `_infer_grist_type()`: Text/Int/Numeric/Date/DateTime/Toggle
4. Chunk records par 100 (paramètre `RECORD_CHUNK_SIZE`)
5. Summary tables: création + masquage raw pages

---

## 5. Configuration

Variables d'environnement (`.env` ou variables):

| Variable | Défaut | Description |
|----------|--------|-------------|
| `VLLM_BASE_URL` | `http://172.17.0.1:30000` | Endpoint vLLM |
| `VLLM_MODEL` | `Qwen/Qwen3.6-35B-A3B-FP8` | Modèle LLM |
| `VLLM_TIMEOUT` | `300` | Timeout LLM (s) |
| `GRIST_SERVER` | `http://localhost:8484` | Serveur Grist |
| `GRIST_API_KEY` | *(vide)* | Clé Bearer |
| `API_TIMEOUT` | `30` | Timeout HTTP (s) |
| `DEBUG` | `True` | Sorties debug |
| `EXCEL_MAX_ROWS` | `10000` | Lignes max Excel |
| `CORRELATION_SUMMARY_MAX_TABLES` | `4` | Tables synthèse max |
| `CORRELATION_SUMMARY_MAX_GROUPS` | `25` | Groupes max par synthèse |

---

## 6. Web UI

### 6.1 Architecture

```
Browser
  │  POST /upload (.xlsx)
  │  GET  /stream/{sid}       ← Server-Sent Events
  │  POST /checkpoint1/{sid}
  │  POST /checkpoint2/{sid}
  │  GET  /refine/{sid}
  │  POST /refine/{sid}
  │
FastAPI (webui/server.py)
  │
  ├── SessionStore             In-memory dict[sid → PipelineSession]
  │     PipelineSession:
  │       event_queue          Queue<(event, json)> — SSE source
  │       checkpoint1/2_event  threading.Event — blocks pipeline thread
  │       cached_profile        DataProfile après Phase 1
  │       cached_classification ClassificationResult après Phase 1
  │       cached_insights       list[InsightEntry] (full, pré-filtrage CP2)
  │       cached_tmp_path       Chemin fichier temporaire (.xlsx)
  │
  ├── WebCheckpointHandler     Satisfait le protocole CheckpointHandler
  │     on_classification()    Émet "checkpoint_1", bloque sur Event
  │     on_insights()          Émet "checkpoint_2", cache insights, bloque
  │
  └── pipeline_runner.py
        run_pipeline()         Phase 1+2 complètes (upload → Grist)
        run_refinement()       Phase 2 seule (depuis cache Phase 1)
        _grist_steps()         Import Grist + ArchetypeEngine + complete event
        start_pipeline_thread()   Thread daemon Phase 1+2
        start_refinement_thread() Thread daemon Phase 2
```

### 6.2 Flux Phase 1 (pipeline complet)

```
Browser → POST /upload → start_pipeline_thread()
   └→ run_pipeline():
        1. DataAnalyzer.analyze(tmp_path)
        2. PipelineOrchestrator.run(profile)  ← bloque sur CP1 + CP2
        3. session.cached_profile = profile
        4. session.cached_classification = result.classification
        5. _grist_steps()  → SSE "complete" avec qualité
```

### 6.3 Flux Phase 2 (affinement)

```
Browser → GET /refine/{sid}  → cached_insights + last intent
Browser → POST /refine/{sid} → start_refinement_thread(intent, selected_insights)
   └→ run_refinement():
        1. PipelineOrchestrator.run_from_insights(
             cached_profile, cached_classification,
             selected_insights, intent)
           ↳ Saute DataAnalyzer, DomainClassifier, InsightExtractor
           ↳ Relance ColumnRelevanceFilter → FeatureEngineer → ...
        2. _grist_steps() → SSE "complete"
```

### 6.4 Démarrage

```bash
./start-grist.sh    # Grist Docker
./start-webui.sh    # FastAPI (http://localhost:8000)
```

Variables d'environnement :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `WEBUI_HOST` | `0.0.0.0` | Adresse d'écoute |
| `WEBUI_PORT` | `8000` | Port HTTP |

---

## 7. CLI Usage

```bash
# Exécution complète
uv run python main.py --input samples/employees_rh.xlsx

# Dry-run (affiche DashboardPlan JSON sans créer Grist)
uv run python main.py --input samples/demo_data.xlsx --dry-run

# Debug (payloads JSON détaillés)
uv run python main.py --input samples/sites_geo_validation.xlsx --debug

# Sortie personnalisée
uv run python main.py --input data.xlsx --output ./results/
```

---

## 8. Données de Test

| Fichier | Description |
|---------|-------------|
| `sample_employees.xlsx` | Cas simple démo |
| `employees_rh.xlsx` | Scenario RH complet (fragile formules) |
| `demo_data.xlsx` | Scenario générique |
| `sites_geo_validation.xlsx` | Validation page carte (geo) |

---

## 9. Limites Connues

- **Formules FeatureEngineer** peuvent échouer HTTP 400 Grist
  (références tables/colonnes ambiguës)
- **Line charts** filtrés si axe x ou y manquant
- **Carte géographique** uniquement si colonnes lat/lon détectées
- Le pipeline **continue malgré erreurs partielles**

---

## 10. Principes de Développement

- **Ajouter un archetype**: fichier dans `archetypes/`, hérite de
  `BaseArchetype`, enregistré dans `ARCHETYPE_MAP`
- **Tests**: `uv run pytest`
- **Debug**: `--debug` affiche payloads JSON de chaque étape
- **Dry-run**: `--dry-run` affiche DashboardPlan JSON sans créer Grist
- **Sécurité**: pas de secrets versionnés (`.env`, `.grist`, credentials)
