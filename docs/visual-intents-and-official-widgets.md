# Visual Intents et Widgets Officiels

Ce document décrit le flux technique qui transforme l'analyse d'un classeur Excel en pages Grist enrichies par des widgets officiels.

## Objectif

Le système ne choisit pas ses visualisations premium à partir d'une liste de règles figées par domaine métier. Il part de l'analyse réelle du classeur et construit des intentions visuelles génériques, ensuite matérialisées dans Grist quand elles sont suffisamment sûres.

En pratique, cela permet:

- d'éviter un rendu trop spécifique au RH;
- de promouvoir des widgets officiels Grist quand ils sont justifiés;
- de conserver un dashboard cohérent même si aucun widget premium n'est applicable.

## Vue d'ensemble du flux

```text
DataAnalyzer
  -> calcule profile.summary_tables
  -> profile.columns / stats / markdown_summary

DomainClassifier
  -> classification.archetype
  -> classification.table_mapping

InsightExtractor
  -> insight report

VisualIntentResolver
  -> visual_intents.intents
  -> visual_intents.promoted_intent_index
  -> visual_intents.promoted_widget

DashboardComposer
  -> DashboardPlan standard
  -> ajoute la page Syntheses croisees

GristImporter
  -> importe les feuilles Excel
  -> importe les tables de synthèse
  -> masque les pages raw auto-créées pour ces tables

ArchetypeEngine / BaseArchetype
  -> rend les sections standards
  -> injecte un widget officiel promu si applicable
  -> matérialise d'autres pages premium Map / Markdown
```

## 1. Tables de synthèse dans DataAnalyzer

Le module [core/data_analyzer.py](core/data_analyzer.py) calcule désormais des tables de synthèse précalculées à partir de couples:

- colonne catégorielle exploitable;
- colonne numérique exploitable.

Le but n'est plus d'exposer plusieurs matrices de corrélation techniques, mais de produire un petit nombre de tables métier lisibles, orientées comparaison.

Points importants:

- les colonnes identifiants sont écartées des métriques;
- les catégories avec trop peu ou trop de modalités sont filtrées;
- un score priorise les synthèses les plus pertinentes;
- le nombre final de tables est borné par la configuration.

Le résultat est stocké dans `DataProfile.summary_tables`.

## 2. Résolution déterministe des visual intents

Le module [core/visual_intents.py](core/visual_intents.py) construit un `VisualIntentPlan` à partir de trois sources:

- le profil du classeur;
- la classification métier;
- les insights.

Les types d'intentions actuellement supportés sont:

- `cross_tab`;
- `trend`;
- `geo`;
- `narrative`;
- `entity_detail`.

Chaque intention décrit notamment:

- la table source;
- les colonnes concernées;
- une priorité;
- une confiance;
- les widgets standards possibles;
- les widgets premium possibles;
- le widget préféré;
- les métadonnées nécessaires à la matérialisation.

### Sélection d'un widget premium promu

Le résolveur calcule aussi un candidat premium principal.

Le score tient compte de:

- la priorité de l'intention;
- sa confiance;
- son type, par exemple `trend`, `cross_tab` ou `geo`;
- sa présentation, par exemple `hero_chart`, `summary_page` ou `geo_page`.

Ce mécanisme permet de n'injecter qu'un seul widget premium promu dans le flux principal du dashboard, au lieu de multiplier les widgets avancés partout.

## 3. Composition du DashboardPlan

Le module [core/dashboard_composer.py](core/dashboard_composer.py) conserve un rôle hybride:

- il demande au LLM un `DashboardPlan` standard;
- il applique ensuite des garde-fous déterministes.

Les garde-fous importants sont:

- suppression des charts sans `chart_type`;
- suppression des line charts sans axe `x` ou `y`;
- ajout d'une page unique `Syntheses croisees`.

### Pourquoi une seule page Syntheses croisees

Les premières itérations créaient plusieurs pages à partir des corrélations. Ce comportement rendait le document difficile à parcourir. Le composer regroupe maintenant les synthèses dans une seule page utilisateur.

Si des `visual_intents` de type `cross_tab` sont disponibles, ils sont utilisés comme source de vérité pour cette page. Sinon, le composer retombe sur `summary_tables`.

## 4. Import Grist des tables de synthèse

Le module [core/grist_importer.py](core/grist_importer.py) importe:

- les feuilles Excel d'origine;
- les tables de synthèse précalculées.

Chaque table de synthèse devient une vraie table Grist. En revanche, les pages raw générées automatiquement pour ces tables sont ensuite masquées afin de ne pas polluer la navigation.

Conséquence:

- les données restent présentes et interrogeables dans le document;
- l'utilisateur final n'est pas exposé à plusieurs onglets techniques inutiles.

## 5. Matérialisation des widgets officiels

Le coeur de la matérialisation se trouve dans [archetypes/base.py](archetypes/base.py).

Les widgets officiels actuellement pris en charge sont:

- `@gristlabs/widget-chart` pour les visualisations avancées;
- `@gristlabs/widget-map#map` pour la carte;
- `@gristlabs/widget-markdown` pour les blocs narratifs.

### Récupération des définitions de widgets

Le client [core/grist_api.py](core/grist_api.py) interroge le catalogue via `GET /api/widgets`. Les définitions récupérées sont ensuite réutilisées pour créer des sections custom conformes à ce qu'attend Grist.

### Structure de persistance

Une section officielle est créée comme section custom dans `_grist_Views_section` avec:

- `parentKey = "custom"`;
- `options.customView` sérialisé comme JSON imbriqué;
- `widgetId`, `widgetDef`, `access`, `pluginId` et autres champs nécessaires.

Point critique:

- `customView.columnsMapping` doit contenir des `colRef` numériques;
- utiliser des noms de colonnes ou des `colId` casse le mapping côté Grist.

### Widget Advanced Chart

Le widget avancé est injecté une seule fois comme widget promu, en priorité sur la page `Syntheses croisees` lorsqu'il s'agit d'un intent `cross_tab`.

Cela permet:

- de garder une page de synthèse compacte;
- d'éviter plusieurs pages premium concurrentes;
- de montrer une visualisation plus riche seulement quand elle a un bon score.

### Widget Map

Le widget Map est matérialisé quand une table contient au minimum:

- une latitude exploitable;
- une longitude exploitable;
- une colonne de label pour `Name`.

Des colonnes optionnelles peuvent aussi être mappées, par exemple:

- `Address`;
- `Geocode`;
- `GeocodedAddress`.

Le niveau d'accès utilisé est `read table`.

### Widget Markdown

Le widget Markdown s'appuie sur une petite table auxiliaire générée à la volée. Cette table contient un champ texte servant de source au contenu narratif.

Le mapping important est:

- `Content` vers la colonne texte de cette table auxiliaire.

Le niveau d'accès utilisé est `full`, ce qui permet au widget de fonctionner correctement dans ce scénario.

## 6. Rôle de GenericArchetype et d'ArchetypeEngine

Le moteur [core/archetype_engine.py](core/archetype_engine.py) transmet le `VisualIntentPlan` à l'archetype choisi.

L'implémentation générique dans [archetypes/generic.py](archetypes/generic.py):

- crée les pages demandées par le `DashboardPlan`;
- rend les sections standard table, chart, card list et form;
- saute les sections invalides plutôt que d'échouer brutalement;
- tente d'ajouter le widget premium promu une seule fois;
- matérialise ensuite les pages premium supplémentaires, notamment Map et Markdown.

Cette stratégie donne un comportement robuste:

- le dashboard standard existe même si un widget officiel échoue;
- les erreurs restent localisées à une section ou une page premium.

## 7. Garde-fous importants

### Filtrage des line charts incomplets

Un line chart sans axe `x` ou `y` est écarté avant validation du plan. Cela évite la création de sections Grist partiellement configurées.

### Dégradation progressive

Si un intent premium ne peut pas être matérialisé:

- le dashboard standard reste rendu;
- la page `Syntheses croisees` reste disponible via ses tables;
- la navigation du document reste propre.

### Debug des colonnes dérivées

Les payloads envoyés par `FeatureEngineer` pour `add_columns()` sont journalisés en mode debug. C'est utile parce que les formules générées sont encore la partie la plus fragile du pipeline, en particulier sur certains classeurs RH.

## 8. Validations couvertes

Le dépôt contient des tests et validations ciblées sur ce flux, notamment pour:

- la propagation de `summary_tables` et `visual_intents` dans le pipeline;
- l'ajout de la page `Syntheses croisees`;
- le filtrage des line charts invalides;
- la persistance des mappings de widgets en `colRef` numériques;
- l'import et le masquage des tables de synthèse;
- la résolution et la promotion des visual intents.

Les classes de test les plus directement liées sont dans:

- [tests/test_visual_intents.py](tests/test_visual_intents.py);
- [tests/test_dashboard_composer.py](tests/test_dashboard_composer.py);
- [tests/test_archetype_engine.py](tests/test_archetype_engine.py);
- [tests/test_grist_importer.py](tests/test_grist_importer.py);
- [tests/test_pipeline.py](tests/test_pipeline.py).

## 9. Limites actuelles

- les formules générées pour les colonnes dérivées peuvent encore échouer sur des jeux de données ambigus;
- la matérialisation Map dépend fortement de la qualité des colonnes géographiques détectées;
- un seul widget premium est promu dans le flux principal afin d'éviter une UI trop chargée.

## 10. Troubleshooting FeatureEngineer

### Symptôme

Le pipeline termine, mais certaines colonnes dérivées ne sont pas créées. En mode debug, cela se manifeste généralement par une erreur HTTP `400` lors de l'appel à `add_columns()`.

### Cause la plus probable

La structure du payload est correcte, mais la formule Grist générée n'est pas acceptée par le moteur Grist.

Les causes les plus fréquentes sont:

- nom de table utilisé dans un `lookupRecords()` qui ne correspond pas exactement au nom Grist réel;
- nom de colonne référencé de manière imprécise ou avec une variante non présente dans le document;
- formule valide en Python général, mais invalide dans le dialecte de formules Grist;
- ambiguïté dans le mapping sémantique quand plusieurs tables ou colonnes se ressemblent.

### Vérification rapide

Lancer le pipeline en debug:

```bash
uv run python main.py --input samples/employees_rh.xlsx --debug
```

Puis vérifier dans les logs:

- `semantic_table` et `table_id`;
- l'URL visée pour l'ajout de colonnes;
- le contenu de `payload.columns[0].fields.formula`.

### Méthode de diagnostic

1. Repérer la colonne échouée dans la liste `failed`.
2. Relever la formule exacte affichée dans le payload debug.
3. Comparer les noms de tables et colonnes utilisés avec ceux présents dans `classification.table_mapping` et dans les tables réellement importées.
4. Vérifier que les références Grist suivent bien les conventions attendues, par exemple `$ColName` et `Table.lookupRecords(...)`.

### Interprétation

Si la requête part bien vers `POST /tables/{tableId}/columns` mais échoue en `400`, le problème n'est généralement plus le transport API. Il faut corriger la formule produite ou renforcer le prompt de génération.

### Portée actuelle du problème

Le cas encore le plus visible concerne certains classeurs RH. Le pipeline continue malgré ces échecs partiels, ce qui permet de conserver un dashboard utilisable, mais avec moins de colonnes dérivées que prévu.

## 11. Lecture recommandée

- [README.md](README.md)
- [docs/grist-actions-validated.md](docs/grist-actions-validated.md)
- [API_REFERENCE.md](API_REFERENCE.md)