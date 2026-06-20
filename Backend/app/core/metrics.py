from prometheus_client import Counter, Histogram, Gauge

runs_total = Counter("runs_total", "Total runs created", ["outcome", "status"])
runs_active = Gauge("runs_active", "Currently active runs")
llm_calls_total = Counter("llm_calls_total", "Total LLM API calls", ["outcome"])
llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "LLM call latency",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)
mcp_calls_total = Counter("mcp_calls_total", "Total MCP tool calls", ["tool"])
mcp_latency_seconds = Histogram(
    "mcp_latency_seconds",
    "MCP tool call latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
defects_found_total = Counter(
    "defects_found_total", "Total defects found", ["defect_type"]
)
