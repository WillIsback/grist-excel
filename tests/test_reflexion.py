from unittest.mock import MagicMock
from core.reflexion import ReflexionValidator
from core.dashboard_composer import DashboardComposer, DashboardPlan, Page, PageSection
from core.insight_extractor import InsightReport
from core.domain_classifier import ClassificationResult


def _make_plan(sections: list[dict]) -> DashboardPlan:
    return DashboardPlan(pages=[Page(name="Test", sections=[
        PageSection(**s) for s in sections
    ])])


RAW_COLS = {"Employes": ["ID_Employe", "Salaire_Brute", "Manager"]}
ENG_COLS = {"Employes": ["nb_absences", "sans_manager"]}
MAPPING = {"employees": "Employes"}


def test_valid_chart_survives():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{
        "widget": "chart", "title": "T", "chart_type": "bar",
        "table": "employees", "x": "ID_Employe", "y": "Salaire_Brute",
    }])
    result = validator.validate_deterministic(plan)
    assert len(result.pages) == 1
    assert len(result.pages[0].sections) == 1


def test_chart_with_missing_x_col_dropped():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{
        "widget": "chart", "title": "T", "chart_type": "bar",
        "table": "employees", "x": "NonExistent", "y": "Salaire_Brute",
    }])
    result = validator.validate_deterministic(plan)
    assert len(result.pages) == 0  # page dropped (0 sections left)


def test_engineered_col_survives():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{
        "widget": "chart", "title": "T", "chart_type": "pie",
        "table": "employees", "x": "Manager", "y": "nb_absences",
    }])
    result = validator.validate_deterministic(plan)
    assert len(result.pages[0].sections) == 1


def test_card_list_with_valid_table_survives():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{"widget": "card_list", "title": "T", "table": "employees"}])
    result = validator.validate_deterministic(plan)
    assert len(result.pages[0].sections) == 1


def test_card_list_with_unknown_table_dropped():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{"widget": "card_list", "title": "T", "table": "ghost_table"}])
    result = validator.validate_deterministic(plan)
    assert len(result.pages) == 0


def test_empty_page_after_drops_is_removed():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{
        "widget": "chart", "title": "T", "chart_type": "bar",
        "table": "employees", "x": "BadCol", "y": "AlsoBad",
    }])
    result = validator.validate_deterministic(plan)
    assert len(result.pages) == 0


def test_drop_ratio_above_half():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    good = {"widget": "card_list", "title": "Good", "table": "employees"}
    bad1 = {"widget": "chart", "title": "B1", "chart_type": "bar",
            "table": "employees", "x": "X1", "y": "Y1"}
    bad2 = {"widget": "chart", "title": "B2", "chart_type": "bar",
            "table": "employees", "x": "X2", "y": "Y2"}
    plan = _make_plan([good, bad1, bad2])
    _, drop_ratio = validator._validate_and_count(plan)
    assert drop_ratio > 0.5


def test_validate_triggers_retry_when_over_half_dropped():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)

    good = PageSection(widget="card_list", title="Good", table="employees")
    bad1 = PageSection(widget="chart", title="B1", chart_type="bar",
                       table="employees", x="X1", y="Y1")
    bad2 = PageSection(widget="chart", title="B2", chart_type="bar",
                       table="employees", x="X2", y="Y2")
    original_plan = DashboardPlan(pages=[Page(name="P", sections=[good, bad1, bad2])])

    retry_plan = DashboardPlan(pages=[Page(name="P", sections=[good])])
    mock_composer = MagicMock(spec=DashboardComposer)
    mock_composer.compose.return_value = retry_plan

    mock_classification = MagicMock()
    mock_classification.archetype = "HR"
    mock_classification.table_mapping = MAPPING
    mock_insights = MagicMock()
    mock_insights.insights = []

    result = validator.validate(
        original_plan, mock_classification, mock_insights, mock_composer
    )

    mock_composer.compose.assert_called_once()
    assert len(result.pages[0].sections) == 1
    assert result.pages[0].sections[0].title == "Good"


def test_validate_no_retry_when_under_half_dropped():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    good1 = PageSection(widget="card_list", title="G1", table="employees")
    good2 = PageSection(widget="card_list", title="G2", table="employees")
    bad = PageSection(widget="chart", title="B", chart_type="bar",
                      table="employees", x="BadX", y="BadY")
    plan = DashboardPlan(pages=[Page(name="P", sections=[good1, good2, bad])])

    mock_composer = MagicMock(spec=DashboardComposer)
    result = validator.validate(plan, MagicMock(), MagicMock(), mock_composer)

    mock_composer.compose.assert_not_called()
    assert len(result.pages[0].sections) == 2
