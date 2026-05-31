from types import SimpleNamespace

from app.routers.runs import _visited_cells_from_trail


def test_visited_cells_from_trail_uses_shared_qa_cell_size() -> None:
    trail = [
        SimpleNamespace(x=260.0, y=-250.0),
        SimpleNamespace(x=300.0, y=-300.0),
        SimpleNamespace(x=700.0, y=10.0),
    ]

    assert _visited_cells_from_trail(trail) == {"1,-1": 2, "3,0": 1}
