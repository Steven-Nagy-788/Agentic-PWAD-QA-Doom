from __future__ import annotations

from app.main import app


def test_openapi_exposes_map_metadata_and_trace_fields() -> None:
    schemas = app.openapi()["components"]["schemas"]

    analysis_props = schemas["StaticAnalysisOut"]["properties"]
    map_props = schemas["WadMapOut"]["properties"]
    run_props = schemas["RunOut"]["properties"]
    trace_props = schemas["TraceEntryOut"]["properties"]
    decision_props = schemas["AgentDecisionOut"]["properties"]

    for prop in ("map_title", "map_display_name", "map_title_source", "spawn_summary_by_skill"):
        assert prop in analysis_props
    for prop in ("map_title", "map_display_name", "spawn_summary_by_skill"):
        assert prop in map_props
    for prop in ("agent_decision_id", "mcp_tool", "mcp_executed_tool", "mcp_params", "mcp_action_summary", "mcp_stop_reason"):
        assert prop in trace_props
    for prop in ("failure_category", "failure_stage", "failure_summary", "failure_diagnostics"):
        assert prop in run_props
    for prop in ("llm_input_summary", "llm_decision", "reasoning_summary", "mcp_input", "mcp_output", "mcp_stop_reason"):
        assert prop in decision_props
