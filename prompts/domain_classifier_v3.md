# Domain Classifier — v3 (Few-Shot)

Classify the data profile into a business domain.

Example 1:
Input: sheets=[Employes, Absences], columns Employes=[ID,Nom,Departement,Salaire]
Output: {"archetype":"HR","confidence":0.92,"table_mapping":{"employees":"Employes","absences":"Absences"},"params":{"name_col":"Nom","department_col":"Departement"}}

Example 2:
Input: sheets=[Tickets, Clients], columns Tickets=[ID,Titre,Statut,Agent]
Output: {"archetype":"SUPPORT","confidence":0.87,"table_mapping":{"tickets":"Tickets","customers":"Clients"},"params":{"status_col":"Statut"}}

Now classify the following:
