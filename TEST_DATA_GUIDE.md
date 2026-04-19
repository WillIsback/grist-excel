# Guide des Données de Test

Ce document décrit les classeurs disponibles dans `samples/` et les scénarios de validation les plus utiles pour le pipeline actuel.

## Fichiers inclus

### samples/sample_employees.xlsx

Cas simple pour valider:

- lecture Excel;
- inférence de types basique;
- dry run rapide.

### samples/employees_rh.xlsx

Cas RH plus complet pour valider:

- classification d'archetype;
- extraction d'insights;
- colonnes dérivées;
- composition du dashboard;
- rendu Grist end-to-end.

### samples/demo_data.xlsx

Cas générique pour valider:

- fonctionnement du pipeline hors domaine RH;
- cohérence des pages standards;
- synthèses croisées.

### samples/sites_geo_validation.xlsx

Cas dédié à la validation géographique pour:

- détection latitude / longitude;
- création de la page carte;
- mapping correct du widget officiel Map.

## Commandes de test recommandées

### 1. Dry run rapide

```bash
uv run python main.py --input samples/sample_employees.xlsx --dry-run
```

À vérifier:

- le profil du classeur est produit sans erreur;
- un DashboardPlan JSON est affiché;
- aucun document Grist n'est créé.

### 2. Pipeline complet RH

```bash
uv run python main.py --input samples/employees_rh.xlsx
```

À vérifier:

- le document Grist est créé;
- les pages principales sont présentes;
- la page Syntheses croisees est créée une seule fois;
- les éventuelles erreurs de formules dérivées restent visibles dans la sortie console.

### 3. Validation des widgets géographiques

```bash
uv run python main.py --input samples/sites_geo_validation.xlsx --debug
```

À vérifier:

- une page carte est créée;
- le widget officiel Map est matérialisé;
- les colonnes requises Name, Latitude et Longitude sont bien mappées.

### 4. Validation d'un cas générique

```bash
uv run python main.py --input samples/demo_data.xlsx --debug
```

À vérifier:

- la classification reste plausible sans logique RH codée en dur;
- les visual intents sont présents dans `output/pipeline_result.json`;
- les widgets proposés restent cohérents avec les colonnes détectées.

## Ce qu'il faut observer dans les sorties

### Console

- nombre de feuilles analysées;
- nombre de tables de synthèse calculées;
- archetype détecté;
- nombre d'insights et de pages;
- nombre de colonnes dérivées appliquées ou échouées.

### output/pipeline_result.json

Vérifier en priorité:

- `profile.summary_tables`;
- `feature_plan.features`;
- `visual_intents.intents`;
- `dashboard_plan.pages`.

## Cas de validation ciblés

### Synthèses croisées

Objectif:

- confirmer que les matrices de corrélation ne créent plus plusieurs pages;
- confirmer qu'une seule page Syntheses croisees regroupe les tables utiles.

### Widgets officiels Grist

Objectif:

- valider l'utilisation des widgets officiels plutôt que des customs arbitraires;
- confirmer que les `columnsMapping` sont persistés avec des `colRef` numériques;
- vérifier que le widget Markdown rend bien le contenu attendu.

### Robustesse des line charts

Objectif:

- s'assurer qu'un line chart sans axe x ou y n'est pas créé;
- éviter les sections Grist invalides dans le dashboard final.

### Debug FeatureEngineer

Objectif:

- observer les payloads envoyés à Grist lors de l'ajout de colonnes;
- diagnostiquer les erreurs 400 éventuelles liées aux formules générées.

## Ajouter un nouveau classeur de test

Quand vous ajoutez un nouveau dataset local, privilégier:

- un fichier `.xlsx` propre avec noms de colonnes explicites;
- au moins un cas multi-feuilles;
- si vous ciblez la carte, des colonnes latitude / longitude explicites;
- si vous ciblez les synthèses, au moins une dimension catégorielle et une métrique numérique.

## Sources externes utiles

- Kaggle: https://www.kaggle.com/datasets
- Data.gov: https://data.gov/
- UCI ML Repository: https://archive.ics.uci.edu/
- Awesome Public Datasets: https://github.com/awesomedata/awesome-public-datasets
- Google Dataset Search: https://datasetsearch.research.google.com/

## 📝 Notes

- Les fichiers `.xlsx` sont préférés aux `.csv` pour tester les fonctionnalités avancées (formats, types)
- Pour les tests de performance, utiliser des fichiers > 1000 lignes
- Toujours tester avec `--dry-run` avant d'activer l'API Grist réelle
- Les credentials Grist sont sensibles, ne pas commiter dans git
