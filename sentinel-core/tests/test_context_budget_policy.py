from app.services.context_budget_policy import ContextBudgetPolicy


def test_budget_policy_allocates_ratios():
    b = ContextBudgetPolicy(sessions_ratio=0.2, search_ratio=0.1).allocate(1000)
    assert b.sessions_budget == 200
    assert b.search_budget == 100
