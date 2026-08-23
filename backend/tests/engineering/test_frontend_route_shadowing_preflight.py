from __future__ import annotations

from arkali.engineering.factory.frontend_route_shadowing_preflight import (
    _repair_shadowed_routes,
    _shadowed_route_findings,
)

#: golden-work-096 (session evidence, frozen): a real qwen2.5-coder:14b
#: reproduced this exact, already-clearly-explained defect unchanged
#: across all 4 real frontend_forms attempts, exhausting the stage's full
#: attempt budget.
_SHADOWED_TASKS_APP_JS = (
    "<Switch>"
    "<Route path='/tasks'><h2>Tasks</h2></Route>"
    "<Route path='/tasks/create'><h2>Create Task</h2></Route>"
    "</Switch>"
)


def test_repairs_a_shadowed_route_by_adding_exact() -> None:
    stage_files = {"frontend/src/App.js": _SHADOWED_TASKS_APP_JS}
    repaired = _repair_shadowed_routes(stage_files)
    assert repaired is not None
    assert _shadowed_route_findings(repaired) == []
    assert "<Route exact path='/tasks'>" in repaired["frontend/src/App.js"]
    # The more specific route itself is untouched.
    assert "<Route path='/tasks/create'>" in repaired["frontend/src/App.js"]


def test_repair_is_a_noop_when_nothing_is_shadowed() -> None:
    stage_files = {
        "frontend/src/App.js": (
            "<Switch>"
            "<Route exact path='/tasks'><h2>Tasks</h2></Route>"
            "<Route path='/tasks/create'><h2>Create Task</h2></Route>"
            "</Switch>"
        ),
    }
    assert _repair_shadowed_routes(stage_files) is None


def test_repair_only_touches_the_file_that_needs_it() -> None:
    stage_files = {
        "frontend/src/App.js": _SHADOWED_TASKS_APP_JS,
        "frontend/src/index.js": "ReactDOM.render(<App />, document.getElementById('root'));\n",
    }
    repaired = _repair_shadowed_routes(stage_files)
    assert repaired is not None
    assert repaired["frontend/src/index.js"] == stage_files["frontend/src/index.js"]


def test_repair_fixes_multiple_shadowed_routes_in_the_same_file() -> None:
    stage_files = {
        "frontend/src/App.js": (
            "<Switch>"
            "<Route path='/tasks'><h2>Tasks</h2></Route>"
            "<Route path='/tasks/create'><h2>Create Task</h2></Route>"
            "<Route path='/payments'><h2>Payments</h2></Route>"
            "<Route path='/payments/create'><h2>Create Payment</h2></Route>"
            "</Switch>"
        ),
    }
    repaired = _repair_shadowed_routes(stage_files)
    assert repaired is not None
    assert _shadowed_route_findings(repaired) == []
