from __future__ import annotations

from app.main import app
from app.serializers.run_serializers import RunOut


def _props(schemas: dict, name: str) -> dict:
    s = schemas[name]
    if "properties" in s:
        return s["properties"]
    if "allOf" in s:
        for item in s["allOf"]:
            if "$ref" in item:
                ref = item["$ref"].split("/")[-1]
                return _props(schemas, ref)
    raise KeyError(f"No properties found for {name}")


def test_openapi_exposes_map_metadata_and_trace_fields() -> None:
    schemas = app.openapi()["components"]["schemas"]

    for prop in ("map_title", "map_display_name", "map_title_source", "spawn_summary_by_skill"):
        assert prop in _props(schemas, "StaticAnalysisOut"), f"Missing {prop} in StaticAnalysisOut"
    for prop in ("map_title", "map_display_name", "spawn_summary_by_skill", "map_min_x", "map_max_x", "map_min_y", "map_max_y"):
        assert prop in _props(schemas, "WadMapOut"), f"Missing {prop} in WadMapOut"
    for prop in ("agent_decision_id", "mcp_tool", "mcp_executed_tool", "mcp_params", "mcp_action_summary", "mcp_stop_reason"):
        assert prop in _props(schemas, "TraceEntryOut"), f"Missing {prop} in TraceEntryOut"
    for prop in ("failure_category", "failure_stage", "failure_summary", "failure_diagnostics", "recording_mp4_url", "report_pdf_url"):
        assert prop in RunOut.model_fields, f"Missing {prop} in RunOut"
    for prop in ("llm_input_summary", "llm_decision", "reasoning_summary", "mcp_input", "mcp_output", "mcp_stop_reason"):
        assert prop in _props(schemas, "AgentDecisionOut"), f"Missing {prop} in AgentDecisionOut"
