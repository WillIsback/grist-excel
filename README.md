# Grist Excel to Application Converter

Convertit un fichier Excel en document Grist enrichi avec analyse métier, pages de synthèse, widgets standards et widgets officiels Grist, en s'appuyant sur un pipeline LLM local.

## Vue d'ensemble

Le pipeline prend un classeur Excel et produit:

- une analyse structurée des feuilles, colonnes et statistiques;
- une classification d'archetype métier;
- des insights métier et un plan de colonnes dérivées;
- un plan de dashboard combinant sections classiques et intentions visuelles déterministes;
- un document Grist prêt à l'emploi.

Exemples:

```bash
uv run python main.py --input samples/employees_rh.xlsx
uv run python main.py --input samples/demo_data.xlsx --dry-run
uv run python main.py --input samples/sites_geo_validation.xlsx --debug
```

## Ce que le projet génère aujourd'hui

- pages Grist standards: table, chart, card list, form;
- tables de synthèse précalculées pour remplacer les anciennes matrices de corrélation;
- une page unique Syntheses croisees pour éviter la prolifération de pages;
- widgets officiels Grist matérialisés quand le contexte le justifie:
  - Advanced Charts;
  - Map;
  - Markdown.

La sélection des visualisations premium n'est pas codée par domaine métier. Elle est dérivée de l'analyse du classeur via un résolveur d'intentions visuelles générique.

## Architecture

```text
Excel File
    |
    v
[Data Analyzer]         Profil du classeur, stats, tables de synthèse
    |
    v
[Domain Classifier]     Archetype métier + table mapping
    |
    v
[Insight Extractor]     Insights statistiques et narratifs
    |
    v
[Feature Engineer]      Plan de colonnes dérivées
    |
    v
[VisualIntentResolver]  Intentions visuelles déterministes
    |
    v
[Dashboard Composer]    DashboardPlan + page Syntheses croisees
    |
    v
[Reflexion Validator]   Validation et nettoyage du plan
    |
    v
[Grist Importer]        Import Excel + tables de synthèse dans Grist
    |
    v
[Archetype Engine]      Pages, charts, forms et widgets officiels
    |
    v
Grist Document
```

## Backend LLM

Le projet utilise un backend vLLM local compatible OpenAI. La configuration validée actuellement est basée sur Qwen/Qwen3.6-35B-A3B-FP8. Aucune API externe n'est requise pour l'inférence.

Voir [API_REFERENCE.md](API_REFERENCE.md) pour la référence vLLM détaillée.

## Installation

### Prérequis

- Python 3.11+;
- une instance vLLM disponible sur l'URL configurée;
- une instance Grist disponible sur l'URL configurée.

### Environnement Python

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### Configuration

Le projet charge ses paramètres depuis l'environnement et, si présent, depuis `.env`.

Variables les plus utiles:

| Variable | Défaut | Description |
|---|---|---|
| `VLLM_BASE_URL` | `http://172.17.0.1:30000` | Endpoint vLLM |
| `VLLM_MODEL` | `Qwen/Qwen3.6-35B-A3B-FP8` | Modèle utilisé pour le pipeline |
| `VLLM_TIMEOUT` | `300` | Timeout LLM en secondes |
| `GRIST_SERVER` | `http://localhost:8484` | URL du serveur Grist |
| `GRIST_API_KEY` | vide | Clé API Grist |
| `API_TIMEOUT` | `30` | Timeout HTTP général |
| `DEBUG` | `True` | Active les sorties debug détaillées |
| `CORRELATION_SUMMARY_MAX_TABLES` | `4` | Limite de tables de synthèse de corrélation |
| `CORRELATION_SUMMARY_MAX_GROUPS` | `25` | Limite de groupes par synthèse |

## Utilisation

### Exécution complète

```bash
uv run python main.py --input samples/employees_rh.xlsx
```

Sorties principales:

- un document Grist créé sur le serveur cible;
- un fichier `output/pipeline_result.json` contenant le résultat du pipeline.

### Dry run

```bash
uv run python main.py --input samples/demo_data.xlsx --dry-run
```

Affiche le DashboardPlan JSON sans créer de document Grist.

### Mode debug

```bash
uv run python main.py --input samples/sites_geo_validation.xlsx --debug
```

Active l'affichage JSON détaillé des étapes du pipeline et des payloads utiles au diagnostic, notamment côté FeatureEngineer.

### Dossier de sortie personnalisé

```bash
uv run python main.py --input samples/demo_data.xlsx --output ./results
```

## Jeux de données inclus

Le dossier `samples/` contient des classeurs utiles pour les validations locales:

- `sample_employees.xlsx`: cas simple de démonstration;
- `employees_rh.xlsx`: scénario RH complet;
- `demo_data.xlsx`: scénario générique;
- `sites_geo_validation.xlsx`: validation de la page carte.

Voir [TEST_DATA_GUIDE.md](TEST_DATA_GUIDE.md) pour les scénarios de test détaillés.

## Structure du projet

```text
grist-excel/
├── main.py
├── config.py
├── requirements.txt
├── core/
│   ├── archetype_engine.py
│   ├── dashboard_composer.py
│   ├── data_analyzer.py
│   ├── domain_classifier.py
│   ├── feature_engineer.py
│   ├── grist_api.py
│   ├── grist_importer.py
│   ├── insight_extractor.py
│   ├── pipeline.py
│   ├── reflexion.py
│   └── visual_intents.py
├── archetypes/
├── prompts/
├── templates/widgets/
├── samples/
├── tests/
├── docs/
└── output/
```

## Notes d'implémentation Grist

- les tables de synthèse sont importées comme vraies tables Grist, mais leurs pages raw auto-créées sont masquées;
- la page utilisateur visible reste Syntheses croisees;
- les widgets officiels sont stockés comme sections custom avec `options.customView` sérialisé en JSON imbriqué;
- les `columnsMapping` des widgets officiels doivent être persistés avec des `colRef` numériques, pas des noms de colonnes.

Voir aussi [docs/visual-intents-and-official-widgets.md](docs/visual-intents-and-official-widgets.md) pour le détail du flux de matérialisation.

## Limites connues

- certaines formules générées automatiquement peuvent encore échouer selon la qualité ou l'ambiguïté du classeur source;
- les line charts sont filtrés si un axe requis manque, afin d'éviter des sections invalides dans Grist;
- la carte n'est proposée que si des colonnes latitude/longitude exploitables sont détectées.

### Known issues

#### Formules dérivées sur certains classeurs RH

Le point encore le plus fragile concerne les colonnes générées par `FeatureEngineer` sur certains classeurs RH.

- le plan de features peut être valide côté LLM mais produire une formule Grist rejetée par l'API;
- les erreurs apparaissent typiquement en HTTP 400 au moment de `add_columns()`;
- les causes probables sont des références de tables ou de colonnes insuffisamment robustes dans les formules générées;
- le pipeline continue malgré ces échecs partiels et journalise les colonnes appliquées et échouées.

Pour diagnostiquer:

```bash
uv run python main.py --input samples/employees_rh.xlsx --debug
```

Le mode debug affiche les payloads envoyés pour l'ajout de colonnes, ce qui permet d'isoler rapidement la formule fautive.

## Développement

### Lancer les tests

```bash
uv run pytest
```

### Tests ciblés utiles

```bash
uv run pytest tests/test_visual_intents.py tests/test_dashboard_composer.py
uv run pytest tests/test_archetype_engine.py tests/test_grist_importer.py
```

### Ajouter un nouvel archetype

1. Créer un module dans `archetypes/` qui hérite de `BaseArchetype`.
2. L'enregistrer dans le moteur d'archetypes.
3. Ajouter ou ajuster les prompts si nécessaire.
4. Ajouter les tests couvrant le rendu visuel attendu.

## Sécurité

- ne pas versionner `.env` ni des secrets Grist;
- ne pas versionner les documents `.grist` générés ni les credentials de sortie;
- considérer les fichiers Excel de test comme potentiellement sensibles.

## Licence

Usage privé / interne.
