# Insight Extractor — v4 (Chain-of-Thought)

Extract insights step by step:
1. List all sheets and their columns
2. For each column, identify its type (categorical, numeric, datetime, text)
3. For categorical columns, suggest distribution insights
4. For datetime columns, suggest trend insights
5. For numeric columns, suggest aggregation insights
6. Cross-reference tables to find relationship insights
7. Rank by business value, keep top 5

Then output ONLY the final JSON.
