Generate a structured Doom PWAD QA report from the supplied JSON summary.

Do not invent raw tick data. Use only the static analysis, aggregate run stats,
defects, notable events, first ticks, and last ticks provided.

Return ONLY valid JSON with these fields:

{
  "report_purpose": "...",
  "test_items_summary": "...",
  "test_environment_summary": "...",
  "defect_summary_narrative": "...",
  "pass_fail_summary": {
    "map_navigation": "PASS or FAIL",
    "combat_engagement": "PASS or FAIL",
    "resource_balance": "PASS or FAIL",
    "secret_coverage": "PASS or FAIL"
  }
}
