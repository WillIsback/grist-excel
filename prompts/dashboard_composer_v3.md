# Dashboard Composer — v3 (Few-Shot)

Compose a dashboard plan from classification and insights.

Example 1 (HR domain):
Input: archetype=HR, insights=[distribution: headcount by dept, trend: absences over time]
Pages: [
  {name: "Dashboard RH", sections: [
    {widget: "chart", chart_type: "bar", table: "Employes", x: "Departement", agg: "count", title: "Effectifs par département"},
    {widget: "chart", chart_type: "line", table: "Absences", x: "Date_Debut", agg: "sum", title: "Absences dans le temps"}
  ]},
  {name: "Employés", sections: [{widget: "card_list", table: "Employes", title: "Annuaire"}]},
  {name: "Saisie", sections: [{widget: "form", table: "Employes", title: "Nouvel employé"}]}
]

Now compose for the following:
