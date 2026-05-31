"""initial schema

Revision ID: 20260522_0001
Revises:
Create Date: 2026-05-22
"""

from __future__ import annotations

from pathlib import Path
import re

from alembic import op

revision = "20260522_0001"
down_revision = None
branch_labels = None
depends_on = None


def _split_sql_statements(script: str) -> list[str]:
    """Split bootstrap SQL without breaking quoted text or dollar blocks."""
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    dollar_tag: str | None = None
    line_comment = False
    block_comment = False
    index = 0
    while index < len(script):
        if dollar_tag is not None:
            if script.startswith(dollar_tag, index):
                current.append(dollar_tag)
                index += len(dollar_tag)
                dollar_tag = None
            else:
                current.append(script[index])
                index += 1
            continue

        char = script[index]
        next_char = script[index + 1] if index + 1 < len(script) else ""
        if line_comment:
            current.append(char)
            index += 1
            if char == "\n":
                line_comment = False
            continue
        if block_comment:
            current.append(char)
            index += 1
            if char == "*" and next_char == "/":
                current.append(next_char)
                index += 1
                block_comment = False
            continue
        if quote is not None:
            current.append(char)
            index += 1
            if char == quote:
                if index < len(script) and script[index] == quote:
                    current.append(script[index])
                    index += 1
                else:
                    quote = None
            continue
        if char == "-" and next_char == "-":
            current.extend((char, next_char))
            index += 2
            line_comment = True
            continue
        if char == "/" and next_char == "*":
            current.extend((char, next_char))
            index += 2
            block_comment = True
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "$":
            match = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", script[index:])
            if match:
                dollar_tag = match.group(0)
                current.append(dollar_tag)
                index += len(dollar_tag)
                continue
        if char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def upgrade() -> None:
    schema_path = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"
    for statement in _split_sql_statements(schema_path.read_text()):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS defects CASCADE")
    op.execute("DROP TABLE IF EXISTS test_reports CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_position_trail CASCADE")
    op.execute("DROP TABLE IF EXISTS notable_event_screenshots CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_decisions CASCADE")
    op.execute("DROP TABLE IF EXISTS game_events CASCADE")
    op.execute("DROP TABLE IF EXISTS test_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS static_analysis_results CASCADE")
    op.execute("DROP TABLE IF EXISTS wad_files CASCADE")
