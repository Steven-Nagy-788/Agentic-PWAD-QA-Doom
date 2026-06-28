from __future__ import annotations

from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_wads: int
    total_runs: int
    total_defects: int
    avg_coverage_pct: float | None
    avg_kill_rate_pct: float | None
    total_llm_cost_usd: float
    runs_by_status: dict[str, int]
    runs_by_outcome: dict[str, int]


class DashboardRecentRun(BaseModel):
    id: str
    map_name: str
    wad_filename: str
    outcome: str | None
    difficulty_level: int | None
    coverage_pct: float | None
    total_kills: int | None
    spawned_enemies: int | None
    defect_count: int
    duration_seconds: float | None
    created_at: str
    llm_cost_usd: float


class DefectTypeBreakdown(BaseModel):
    defect_type: str
    count: int
    avg_severity: float


class DefectSeverityBreakdown(BaseModel):
    severity: int
    count: int


class DashboardDefectSummary(BaseModel):
    by_type: list[DefectTypeBreakdown]
    by_severity: list[DefectSeverityBreakdown]
    total_defects: int


class DashboardHealthOverview(BaseModel):
    api_status: str
    gemini_configured: bool
    mcp_reachable: bool | None
    db_status: str
    storage_total_bytes: int
    storage_total_files: int
    active_runs: int
