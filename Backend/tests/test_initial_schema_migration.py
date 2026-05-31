from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_initial_migration():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "20260522_0001_initial_schema.py"
    spec = importlib.util.spec_from_file_location("initial_schema_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_split_sql_statements_preserves_dollar_blocks_and_quoted_semicolons() -> None:
    migration = _load_initial_migration()
    statements = migration._split_sql_statements(
        """
        CREATE TABLE sample (value TEXT DEFAULT ';');
        -- semicolon inside a comment ;
        DO $$
        BEGIN
            PERFORM ';';
        END $$;
        CREATE INDEX sample_idx ON sample(value);
        """
    )

    assert len(statements) == 3
    assert statements[0].startswith("CREATE TABLE")
    assert "PERFORM ';';" in statements[1]
    assert statements[2].endswith("CREATE INDEX sample_idx ON sample(value)")
