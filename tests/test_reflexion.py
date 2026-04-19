from core.reflexion import ReflexionValidator
from core.dashboard_composer import DashboardPlan, Page, PageSection


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
