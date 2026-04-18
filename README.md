# Grist Excel to Application Converter

Transform Excel files into structured Grist applications with forms and dashboards using Qwen3.5-122B.

## Architecture

### Phase 1: Infrastructure (Already Done)
- **Model**: Qwen3.5-122B via vLLM (port 30000)
- **Backend**: FastAPI
- **Context**: 32k tokens support

### Phase 2: Data Ingestion Pipeline
- Excel parsing with pandas/openpyxl
- Metadata extraction (columns, types, samples)
- Smart token-limiting serialization

### Phase 3: Agent Architecture
- **Analyst Agent**: Validates data, asks clarifying questions
- **Architect Agent**: Designs relational schema
- **UI Agent**: Maps to Grist widgets (forms, charts, dashboards)

### Phase 4: Grist Generation
- Python scripts using pygrister or grist-api
- Template-based widget generation
- Syntax validation before API calls

### Phase 5: Optimization
- RAG with Grist examples (Phase 1)
- GRPO fine-tuning (Phase 2, optional)

## Grist Widget Types

1. **Table**: Display many records
2. **Card**: Single record form view
3. **Card List**: Scrollable list of records
4. **Form**: External form for data entry
5. **Chart**: Various chart types (bar, line, pie, etc.)
6. **Calendar**: Event calendar view
7. **Custom**: Embedded web page

## Grist Template Examples Found

### Available Templates for RAG:
- **Finances**:
  - investment-research-template
  - personal-budget
- **Geography**:
  - US National Park Database
- **Inventaires**:
  - lab-inventory-management
- **Projets**:
  - lab-project-management-template
  - recurring-tasks-template

### Example Use Cases from Grist:
- Credit Card Expenses tracking
- Book Lists with library links
- Email preparation with formulas
- Invoice generation
- Payroll tracking
- Mailing labels
- Treasure Hunt planning
- Map visualization
- Task management
- Lead lists
- Timesheets
- Auto time/user stamps
- Proposals & Contracts

## Python Libraries

### Primary: pygrister (ricpol/pygrister)
```python
from pygrister.api import GristApi

grist = GristApi()
# List users
status_code, response = grist.list_doc_users()
# Fetch records
status_code, response = grist.list_records('Table1')
# Add columns
cols = [{'id': 'age', 'fields': {'label': 'age', 'type': 'Int'}}]
status_code, response = grist.add_cols('Table1', cols)
```

### Alternative: grist-api (gristlabs/py_grist_api)
```python
from grist_api import GristDocAPI

api = GristDocAPI(DOC_ID, server=SERVER)
# Add records
rows = api.add_records('Table1', [{'food': 'eggs'}, {'food': 'beets'}])
# Fetch table
data = api.fetch_table('Table1')
```

## Next Steps

1. **Create MVP Prototype** (Priority 1)
   - Simple Excel → Schema → Grist API flow
   - Test with sample Excel file
   - No agents yet, direct LLM call

2. **Add Agent Orchestration** (Priority 2)
   - Implement CrewAI with 3 agents
   - Add validation layer

3. **Build RAG Database** (Priority 3)
   - Download Grist template examples
   - Store in AnythingLLM
   - Create retrieval system

4. **Fine-tuning** (Optional)
   - Only if MVP + RAG not sufficient
   - Use Unsloth on GB10

## File Structure

```
/home/wderue/workspace/grist-excel/
├── README.md
├── core/
│   ├── excel_parser.py
│   ├── schema_generator.py
│   └── grist_client.py
├── agents/
│   ├── analyst.py
│   ├── architect.py
│   └── ui_designer.py
├── templates/
│   └── grist_widgets.json
├── rag/
│   └── grist_examples/
├── tests/
└── main.py
```

## Key Grist API Endpoints

- `GET /api/docs/{docId}/tables` - List tables
- `POST /api/docs/{docId}/tables/{tableName}/records` - Add records
- `PATCH /api/docs/{docId}/tables/{tableName}/columns` - Add/modify columns
- `POST /api/docs/{docId}/views` - Create views
- `POST /api/docs/{docId}/widgets` - Add widgets

## Authentication

- API Key from Grist Profile Settings
- Set via `GRIST_API_KEY` environment variable
- Server: `https://subdomain.getgrist.com`
