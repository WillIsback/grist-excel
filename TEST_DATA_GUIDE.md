# Guide des Données de Test pour Grist Excel Converter

Ce document liste les sources de données Excel pour tester les différentes fonctionnalités du système.

## 📦 Fichiers Samples Inclus

### 1. Données Employés (Déjà créé)
```
samples/sample_employees.xlsx
```
**Contenu**: Liste d'employés avec départements, salaires, dates d'embauche
**Usage**: Test de base, validation du parser Excel

### 2. Données Ventes (À générer)
```
samples/demo_data.xlsx
```
**Contenu**: Commandes de vente avec produits, clients, régions, statuts
**Générer avec**: `python main.py --demo`
**Usage**: Test complet dashboard de vente

---

## 🌐 Sources de Données Excel pour Tests

### 1. **Kaggle Datasets** (Gratuit, varié)
**URL**: https://www.kaggle.com/datasets

**Recommandations**:
- **Sales Dataset**: Recherchez "sales data", "retail data"
- **HR Dataset**: "employee data", "HR analytics"
- **Finance Dataset**: "transaction data", "expense data"

**Exemples concrets**:
- [Superstore Sales Dataset](https://www.kaggle.com/datasets/rohitsahoo/sales-forecasting)
- [Employee Attrition Dataset](https://www.kaggle.com/datasets/arashnic/attrition)
- [E-commerce Data](https://www.kaggle.com/datasets/carrie1/ecommerce-data)

**Format**: Télécharger en `.xlsx` ou `.csv` (convertir en xlsx)

---

### 2. **GitHub Public Datasets** (Gratuit)
**URL**: https://github.com/awesomedata/awesome-public-datasets

**Catégories utiles**:
- Business & Finance
- Government Data
- Healthcare
- Education

**Exemple**: Recherchez "excel dataset github"

---

### 3. **Data.gov** (Données gouvernementales US)
**URL**: https://data.gov/

**Avantages**:
- Données réelles et structurées
- Formats variés (CSV, Excel, JSON)
- Domaines multiples

**Recherche**: Filtrer par format "Excel"

---

### 4. **Google Dataset Search**
**URL**: https://datasetsearch.research.google.com/

**Avantages**:
- Moteur de recherche spécialisé
- Liens vers sources originales
- Métadonnées complètes

---

### 5. **UCI Machine Learning Repository**
**URL**: https://archive.ics.uci.edu/

**Datasets classiques**:
- [Adult Income Dataset](https://archive.ics.uci.edu/ml/datasets/adult)
- [Customer Segmentation](https://archive.ics.uci.edu/ml/datasets/Online+Retail)
- [Credit Card Fraud](https://archive.ics.uci.edu/ml/datasets/credit+card+fraud+detection)

---

## 🎯 Scénarios de Test par Fonctionnalité

### Test 1: Parser Excel Basique
**Fichier**: `samples/sample_employees.xlsx`
**Commande**:
```bash
python main.py --input samples/sample_employees.xlsx --request "Liste simple d'employés" --dry-run
```
**Attendu**:
- ✅ Parsing correct des colonnes
- ✅ Détection des types de données
- ✅ Échantillon extrait correctement

---

### Test 2: Génération de Schema Simple
**Fichier**: `samples/demo_data.xlsx`
**Commande**:
```bash
python main.py --input samples/demo_data.xlsx --request "Tableau de bord de ventes" --dry-run
```
**Attendu**:
- ✅ Schema JSON généré
- ✅ Tables et colonnes détectées
- ✅ Relations suggérées si pertinentes

---

### Test 3: Schema avec Relations
**Fichier**: Télécharger un dataset e-commerce complet
**Source suggérée**: https://www.kaggle.com/datasets/carrie1/ecommerce-data
**Commande**:
```bash
python main.py --input e-commerce-data.xlsx --request "Base de données e-commerce avec relations clients-commandes-produits" --dry-run
```
**Attendu**:
- ✅ Détection des relations entre tables
- ✅ Clés étrangères suggérées
- ✅ Normalisation des données

---

### Test 4: Dashboard avec Widgets
**Fichier**: `samples/demo_data.xlsx`
**Commande**:
```bash
python main.py --input samples/demo_data.xlsx --request "Dashboard de ventes avec graphiques et formulaires" --dry-run
```
**Attendu**:
- ✅ Widgets suggérés (Table, Chart, Form)
- ✅ Formules Python pour calculs
- ✅ Layout structuré

---

### Test 5: Données Complexes avec Dates
**Fichier**: Dataset financier avec transactions
**Source suggérée**: https://www.kaggle.com/datasets/vedavyasv/sample-bank-transactions-dataset
**Commande**:
```bash
python main.py --input transactions.xlsx --request "Suivi de transactions bancaires avec analytique temporelle" --dry-run
```
**Attendu**:
- ✅ Détection correcte des types Date
- ✅ Formules pour calculs temporels
- ✅ Agrégations suggérées

---

### Test 6: Grande Volume de Données
**Fichier**: Dataset avec 1000+ lignes
**Source**: Générer ou télécharger un gros dataset
**Commande**:
```bash
python main.py --input large_dataset.xlsx --request "Analyse de données massives" --dry-run
```
**Attendu**:
- ✅ Limitation intelligente des tokens
- ✅ Échantillonnage représentatif
- ✅ Performance acceptable (< 30s)

---

### Test 7: Données avec Valeurs Null
**Fichier**: Dataset avec champs optionnels
**Commande**:
```bash
python main.py --input incomplete_data.xlsx --request "Gestion de données incomplètes" --dry-run
```
**Attendu**:
- ✅ Gestion des valeurs null/None
- ✅ Suggestions de colonnes optionnelles
- ✅ Pas d'erreur de parsing

---

### Test 8: Intégration Grist Complète
**Fichier**: `samples/demo_data.xlsx`
**Configuration**: Nécessite credentials Grist réels
**Commande**:
```bash
# Définir les credentials dans config.py
export GRIST_API_KEY="your_api_key"
export GRIST_SERVER="https://your-org.getgrist.com"

python main.py --input samples/demo_data.xlsx --request "Application complète de gestion"
```
**Attendu**:
- ✅ Document Grist créé
- ✅ Tables importées
- ✅ Widgets générés

---

## 🛠️ Scripts Utilitaires

### Générer un Dataset de Test
```python
# scripts/generate_test_data.py
import pandas as pd
import numpy as np

# Générer 1000 lignes de données ventes
df = pd.DataFrame({
    'id': range(1, 1001),
    'date': pd.date_range('2026-01-01', periods=1000, freq='H'),
    'produit': np.random.choice(['A', 'B', 'C', 'D'], 1000),
    'quantite': np.random.randint(1, 100, 1000),
    'prix': np.random.uniform(10, 500, 1000),
    'client': np.random.choice(['Client A', 'Client B', 'Client C'], 1000),
    'region': np.random.choice(['Nord', 'Sud', 'Est', 'Ouest'], 1000)
})

df.to_excel('samples/large_sales_data.xlsx', index=False)
```

### Convertir CSV vers XLSX
```bash
# Utiliser pandas
python -c "import pandas as pd; df = pd.read_csv('data.csv'); df.to_excel('data.xlsx', index=False)"
```

---

## 📊 Checklist de Tests

- [ ] Parser Excel: fichier valide
- [ ] Parser Excel: fichier vide
- [ ] Parser Excel: types de données variés
- [ ] Parser Excel: limitation max_rows
- [ ] Parser Excel: gestion erreurs
- [ ] Schema Generator: appel vLLM
- [ ] Schema Generator: parsing JSON
- [ ] Schema Generator: validation Pydantic
- [ ] Schema Generator: gestion erreurs
- [ ] Grist Client: création document (mock)
- [ ] Grist Client: ajout records (mock)
- [ ] Grist Client: création widgets (mock)
- [ ] End-to-end: workflow complet
- [ ] Performance: 1000 lignes < 30s

---

## 🔗 Liens Utiles

- **Kaggle**: https://www.kaggle.com/datasets
- **Data.gov**: https://data.gov/
- **UCI ML Repo**: https://archive.ics.uci.edu/
- **GitHub Datasets**: https://github.com/awesomedata/awesome-public-datasets
- **Google Dataset Search**: https://datasetsearch.research.google.com/

---

## 📝 Notes

- Les fichiers `.xlsx` sont préférés aux `.csv` pour tester les fonctionnalités avancées (formats, types)
- Pour les tests de performance, utiliser des fichiers > 1000 lignes
- Toujours tester avec `--dry-run` avant d'activer l'API Grist réelle
- Les credentials Grist sont sensibles, ne pas commiter dans git
