# Insight Extractor — v3 (Few-Shot)

Extract business insights from the data profile.

Example 1:
Input: sheets=[Employes], columns Employes=[ID,Nom,Departement,Salaire,Date_Embauche]
Output: [{"type":"distribution","title":"Répartition par département","table":"Employes","column":"Departement","agg":"count"},{"type":"trend","title":"Embauches dans le temps","table":"Employes","column":"Date_Embauche","agg":"count"}]

Example 2:
Input: sheets=[Tickets], columns Tickets=[ID,Titre,Statut,CreatedAt,Duree_Moyenne]
Output: [{"type":"distribution","title":"Tickets par statut","table":"Tickets","column":"Statut","agg":"count"},{"type":"outlier","title":"Tickets très longs","table":"Tickets","column":"Duree_Moyenne","threshold":"max"}]

Now extract insights for the following:
