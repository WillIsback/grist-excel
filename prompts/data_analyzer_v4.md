# Data Analyzer — v4 (Chain-of-Thought)

Analyze the Excel file step by step:
1. List all sheet names and row counts
2. For each sheet, enumerate all column names and sample values
3. Infer column types (text, integer, numeric, date, boolean)
4. Compute statistics: count, null_percentage, unique_count, min/max for numerics
5. Detect relationships: find columns shared across sheets or with matching value ranges
6. Summarize findings in plain language

Then output ONLY the final JSON.
