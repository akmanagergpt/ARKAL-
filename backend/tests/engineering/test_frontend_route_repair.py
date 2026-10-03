from arkali.engineering.factory.frontend_ux_preflight import (
    _repair_unreachable_parameterized_routes,
    _unreachable_parameterized_route_findings,
)


def test_unreachable_parameterized_route_repair_removes_only_dead_self_closing_route() -> None:
    files = {
        "frontend/src/App.js": "<Route path='/tasks/delete/:id' element={<DeleteTask />} />\\n",
        "frontend/src/TaskList.js": "export default function TaskList(){ return <div>Tasks</div>; }",
    }
    repaired = _repair_unreachable_parameterized_routes(files)
    assert "<Route path='/tasks/delete/:id'" not in repaired["frontend/src/App.js"]
    assert _unreachable_parameterized_route_findings(repaired) == []


def test_reachable_parameterized_route_is_preserved() -> None:
    files = {
        "frontend/src/App.js": "<Route path='/tasks/edit/:id' element={<EditTask />} />\\n",
        "frontend/src/TaskList.js": "export function TaskList(){ return <Link to={'/tasks/edit/' + task.id}>Edit</Link>; }",
    }
    repaired = _repair_unreachable_parameterized_routes(files)
    assert "/tasks/edit/:id" in repaired["frontend/src/App.js"]
