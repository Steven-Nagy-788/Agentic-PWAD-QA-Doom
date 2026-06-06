import { expect, test, type Page } from "@playwright/test";

const run = {
  id: "e2e-live",
  wad_file_id: "wad-e2e",
  static_analysis_id: null,
  map_name: "MAP01",
  map_display_name: "MAP01",
  difficulty_level: 3,
  iwad_used: "freedoom2",
  llm_model: "deterministic",
  max_ticks: 180,
  seed: 42,
  status: "running",
  started_at: new Date().toISOString(),
  completed_at: null,
  duration_seconds: null,
  outcome: null,
  final_hp: 100,
  final_armor: 0,
  total_kills: 0,
  secrets_found: 0,
  total_items_collected: 0,
  total_actions_taken: 2,
  total_llm_calls: 2,
  recording_metadata: { quality_status: "ok" },
  behavior_profile: "fast",
  progress_metrics: { coverage_percent: 12.5 },
  agent_quality_flags: { quality_status: "ok", warnings: [] },
  environment_metadata: {},
  report_pdf_url: null,
  recording_mp4_url: null,
  created_at: new Date().toISOString(),
};

const map = {
  wad_file_id: "wad-e2e",
  map_name: "MAP01",
  iwad_required: "doom2",
  analyzed: true,
  map_min_x: -512,
  map_max_x: 512,
  map_min_y: -512,
  map_max_y: 512,
};

async function stubLiveRun(page: Page) {
  await page.addInitScript(() => {
    const NativeWebSocket = window.WebSocket;
    class MockRunWebSocket extends EventTarget {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;
      readyState = MockRunWebSocket.CONNECTING;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      constructor(public url: string) {
        super();
        setTimeout(() => {
          this.readyState = MockRunWebSocket.OPEN;
          const event = new Event("open");
          this.onopen?.(event);
          this.dispatchEvent(event);
        }, 0);
      }
      send() {}
      close() {
        this.readyState = MockRunWebSocket.CLOSED;
        const event = new CloseEvent("close");
        this.onclose?.(event);
        this.dispatchEvent(event);
      }
    }
    function WebSocketProxy(url: string | URL, protocols?: string | string[]) {
      if (String(url).includes("/ws/runs/")) {
        return new MockRunWebSocket(String(url));
      }
      return new NativeWebSocket(url, protocols);
    }
    Object.assign(WebSocketProxy, NativeWebSocket, {
      CONNECTING: NativeWebSocket.CONNECTING,
      OPEN: NativeWebSocket.OPEN,
      CLOSING: NativeWebSocket.CLOSING,
      CLOSED: NativeWebSocket.CLOSED,
    });
    Object.defineProperty(window, "WebSocket", { value: WebSocketProxy });
  });

  await page.route("**/api/v1/runs/e2e-live/live-snapshot", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        run,
        state: { type: "state", tick: 64, health: 100, armor: 0, kills: 0, secrets: 0, position: { x: 80, y: -120, angle: 90 } },
        decisions: [],
        trace: [],
        events: [],
        position_trail: [
          { id: 1, run_id: "e2e-live", tick_number: 1, x: -300, y: -120, health: 100 },
          { id: 2, run_id: "e2e-live", tick_number: 40, x: 20, y: 40, health: 100 },
        ],
        defects: [],
        usage: { total_llm_calls: 2, total_prompt_tokens: 100, total_completion_tokens: 20, estimated_cost_usd: 0.0001 },
        progress_metrics: { coverage_percent: 12.5 },
        agent_quality_flags: { quality_status: "ok", warnings: [] },
        report_status: { status: "pending", pdf_available: false },
        same_run_memory: null,
        visited_cells: { "0,0": 3, "1,0": 1 },
        visited_cell_size: 256,
      }),
    });
  });
  await page.route("**/api/v1/runs/e2e-live", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(run) });
  });
  await page.route("**/api/v1/wads/wad-e2e/maps", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify([map]) });
  });
}

async function expectContainedSquare(page: Page) {
  const viewport = page.getByTestId("map-canvas-viewport");
  const frame = page.getByTestId("map-canvas-frame");
  await expect(frame).toBeVisible();
  const viewportBox = await viewport.boundingBox();
  const frameBox = await frame.boundingBox();
  expect(viewportBox).not.toBeNull();
  expect(frameBox).not.toBeNull();
  expect(frameBox!.width).toBeGreaterThan(120);
  expect(Math.abs(frameBox!.width - frameBox!.height)).toBeLessThanOrEqual(2);
  expect(frameBox!.width).toBeLessThanOrEqual(viewportBox!.width + 1);
  expect(frameBox!.height).toBeLessThanOrEqual(viewportBox!.height + 1);
}

test("live map is fully contained on first paint and after resize", async ({ page }) => {
  await stubLiveRun(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/run/e2e-live");
  await expect(page.getByRole("heading", { name: "Map And Trail" })).toBeVisible();
  await expectContainedSquare(page);

  await page.setViewportSize({ width: 390, height: 760 });
  await expectContainedSquare(page);
});
