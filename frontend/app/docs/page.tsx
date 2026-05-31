"use client";

import { useState } from "react";
import { API_BASE } from "@/lib/api";

export default function DocsPage() {
  const [openSection, setOpenSection] = useState<string | null>("getting-started");
  const toggle = (section: string) => setOpenSection(openSection === section ? null : section);
  return (
    <div className="space-y-5 p-4 lg:p-6 max-w-4xl">
      <h2 className="text-xl font-semibold">Documentation Portal</h2>

      <DocSection id="getting-started" title="Getting Started" open={openSection === "getting-started"} onToggle={toggle}>
        <p className="text-sm text-neutral-600 mb-2">
          The Agentic PWAD QA Doom system automatically tests Doom WAD files by running an AI agent
          through each map and reporting defects.
        </p>
        <ol className="list-decimal list-inside text-sm text-neutral-600 space-y-1">
          <li>Upload a WAD file from the WAD Library view</li>
          <li>Select a map to run the agent on</li>
          <li>Configure difficulty, max ticks, and agent behavior profile</li>
          <li>Launch the run and observe the agent in real-time</li>
          <li>Review defects, decisions, and the recording in the Run Detail view</li>
        </ol>
        <p className="mt-3 text-sm text-neutral-600">
          This graduation-project proof of concept is intended for localhost use only. It does not provide authentication.
        </p>
      </DocSection>

      <DocSection id="api-reference" title="API Reference" open={openSection === "api-reference"} onToggle={toggle}>
        <p className="text-sm text-neutral-500 mb-3">All endpoints are prefixed with <code className="rounded bg-neutral-100 px-1 py-0.5 text-xs">{API_BASE}</code></p>
        <div className="space-y-1 text-sm">
          <ApiEndpoint method="GET" path="/health" desc="Health check" />
          <ApiEndpoint method="GET" path="/health/gemini" desc="Gemini cached status" />
          <ApiEndpoint method="POST" path="/health/gemini/probe" desc="Probe Gemini now" />
          <ApiEndpoint method="GET" path="/health/mcp" desc="MCP Doom server health" />
          <ApiEndpoint method="GET" path="/wads" desc="List all WAD files" />
          <ApiEndpoint method="POST" path="/wads/upload" desc="Upload a WAD file" />
          <ApiEndpoint method="GET" path="/wads/{id}/maps" desc="List maps in a WAD" />
          <ApiEndpoint method="POST" path="/runs" desc="Create a new run" />
          <ApiEndpoint method="GET" path="/runs" desc="List runs" />
          <ApiEndpoint method="GET" path="/runs/{id}" desc="Get run details" />
          <ApiEndpoint method="DELETE" path="/runs/{id}" desc="Cancel a run" />
          <ApiEndpoint method="GET" path="/runs/{id}/trace" desc="Full action trace" />
          <ApiEndpoint method="GET" path="/runs/{id}/events" desc="Filtered events" />
          <ApiEndpoint method="GET" path="/runs/{id}/decisions" desc="LLM decisions" />
          <ApiEndpoint method="GET" path="/runs/{id}/defects" desc="Detected defects" />
          <ApiEndpoint method="GET" path="/runs/{id}/recording" desc="Run recording MP4" />
          <ApiEndpoint method="GET" path="/runs/{id}/report/pdf" desc="Run report PDF" />
          <ApiEndpoint method="GET" path="/runs/compare" desc="Compare two runs" />
          <ApiEndpoint method="GET" path="/settings" desc="App settings (merged env+DB)" />
          <ApiEndpoint method="PATCH" path="/settings" desc="Persist settings to DB" />
          <ApiEndpoint method="GET" path="/settings/behavior-profiles" desc="Behavior profiles" />
          <ApiEndpoint method="GET" path="/runs/{id}/usage" desc="Token usage summary" />
          <ApiEndpoint method="GET" path="/runs/{id}/benchmark" desc="LLM/MCP latency benchmarks" />
          <ApiEndpoint method="GET" path="/metrics" desc="Prometheus metrics" />
        </div>
      </DocSection>

      <DocSection id="architecture" title="Architecture" open={openSection === "architecture"} onToggle={toggle}>
        <p className="text-sm text-neutral-600 mb-2">
          The system consists of these main components:
        </p>
        <ul className="list-disc list-inside text-sm text-neutral-600 space-y-1">
          <li><strong>Frontend</strong> — Next.js dashboard (this UI)</li>
          <li><strong>Backend API</strong> — FastAPI server orchestrating runs</li>
          <li><strong>MCP Doom Server</strong> — Model Context Protocol server bridging LLM decisions to Doom gameplay</li>
          <li><strong>Gemini LLM</strong> — Google&apos;s Gemini model driving agent decisions</li>
          <li><strong>PostgreSQL</strong> — Persisting runs, decisions, events, and defects</li>
          <li><strong>Recording Service</strong> — Captures MP4 recordings of each run</li>
          <li><strong>WebSocket Stream</strong> — Real-time frame + telemetry streaming to the live view</li>
        </ul>
        <div className="mt-4 rounded border border-neutral-200 bg-neutral-50 p-4 text-center text-sm text-neutral-500">
          [Frontend] &harr; [FastAPI Backend] &harr; [MCP-Doom] &harr; [DOOM (Wooff)]
          <br />[Backend] &harr; [PostgreSQL] | [Gemini LLM]
        </div>
      </DocSection>

      <DocSection id="behavior-profiles" title="Behavior Profiles" open={openSection === "behavior-profiles"} onToggle={toggle}>
        <p className="text-sm text-neutral-600 mb-3">
          Behavior profiles control how the agent plays through a map. Each profile
          adjusts throttle delays and the system prompt while recording fidelity remains consistent.
        </p>
        <div className="space-y-3">
          <DocProfileCard name="Thorough" desc="Slow, methodical exploration. Checks every room, every corner. Maximum coverage." />
          <DocProfileCard name="Fast" desc="Covers ground quickly, breadth over depth. Prioritizes exploration speed." />
          <DocProfileCard name="Exploit-focused" desc="Aggressively tests boundaries. Tries to break the map. Jumps, wall-hugs, spam-uses." />
        </div>
      </DocSection>
    </div>
  );
}

function DocSection({ id, title, open, onToggle, children }: { id: string; title: string; open: boolean; onToggle: (id: string) => void; children: React.ReactNode }) {
  return (
    <div className="rounded border border-neutral-200 bg-white">
      <button onClick={() => onToggle(id)} className="flex w-full items-center justify-between px-4 py-3 text-left font-semibold text-sm hover:bg-neutral-50">
        {title}
        <span className={`text-neutral-400 transition ${open ? "rotate-180" : ""}`}>▾</span>
      </button>
      {open ? <div className="border-t border-neutral-200 px-4 py-3">{children}</div> : null}
    </div>
  );
}

function ApiEndpoint({ method, path, desc }: { method: string; path: string; desc: string }) {
  const color = method === "GET" ? "text-emerald-600" : method === "POST" ? "text-blue-600" : method === "DELETE" ? "text-red-600" : "text-neutral-600";
  return (
    <div className="flex items-center gap-3 py-1">
      <span className={`w-16 text-xs font-bold uppercase ${color}`}>{method}</span>
      <code className="flex-1 text-xs text-neutral-700">{path}</code>
      <span className="text-xs text-neutral-500 truncate max-w-[200px]">{desc}</span>
    </div>
  );
}

function DocProfileCard({ name, desc }: { name: string; desc: string }) {
  return (
    <div className="rounded border border-neutral-200 bg-neutral-50 p-3">
      <h4 className="font-semibold text-sm mb-1">{name}</h4>
      <p className="text-xs text-neutral-600">{desc}</p>
    </div>
  );
}
