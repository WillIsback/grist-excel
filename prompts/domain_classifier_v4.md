# Domain Classifier — v4 (Chain-of-Thought)

Classify the data profile step by step:
1. List the sheet names and their key columns
2. Identify domain keywords (employee, ticket, grade, asset, task…)
3. Select the archetype that best matches
4. Map each semantic role to the exact table name
5. Map each semantic param to the exact column name
6. Estimate confidence (0.0–1.0)
7. Return the JSON result

Think through each step explicitly, then output ONLY the final JSON.
