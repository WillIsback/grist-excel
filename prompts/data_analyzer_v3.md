# Data Analyzer — v3 (Few-Shot)

Analyze the Excel file and produce a structured data profile.

Example:
Input: Excel file with sheets "Employes" (100 rows, 5 cols) and "Absences" (50 rows, 4 cols)
Output: {
  "sheets": ["Employes", "Absences"],
  "columns": {"Employes": ["ID", "Nom", "Departement", "Salaire", "Matricule"], "Absences": ["ID", "Employe_ID", "Date_Debut", "Duree_Jours"]},
  "apparent_fk": [{"from": "Absences.Employe_ID", "to": "Employes.ID"}],
  "markdown_summary": "2 sheets, 150 total records, 1 apparent relationship"
}

Now analyze the following:
