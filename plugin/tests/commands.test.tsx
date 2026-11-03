import type { On } from "claude-code";
import { expect, test } from "claude-code/testing";

const BASE = "http://api.test";
const CAMPAIGN = {
  id: "02b38983-5893-4593-83b3-36bab625b6b1",
  name: "Spring Essentials",
  window_start: "2026-05-01",
  window_end: "2026-05-31",
  global_budget_eur: "250000.00",
  market_codes: ["SE"],
  created_at: "2026-11-03T15:24:40Z",
};
const VIEW = {
  campaign: CAMPAIGN,
  markets: [
    {
      plan: {
        id: "a1b2c3d4-0000-4000-8000-000000000001",
        market_code: "SE",
        market_name: "Sweden",
        currency: "SEK",
        start_date: "2026-05-01",
        end_date: "2026-05-31",
        budget_share: "1.0000",
        budget_eur: "250000.00",
        status: "draft",
        version: 1,
      },
      holidays_available: true,
      holidays: [{ date: "2026-05-01", name: "International Workers' Day" }],
      clashes: [
        {
          kind: "launch_on_holiday",
          date: "2026-05-01",
          holiday_name: "International Workers' Day",
        },
      ],
    },
  ],
};

const PANE = {
  plugin: "plan-desk",
  component: "Pane",
  requestId: "plan-desk",
  props: {
    title: "Plan desk",
    isFocused: false,
    bodyColumns: 60,
    placement: "dock",
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const;

const RUN = {
  command: "plan-desk",
  origin: { kind: "composer" },
  presentation: { isFullscreen: false, columns: 120 },
} as const;

type Fake = (url: string, method: string) => { status: number; text: string };

type Registered = { name: string; isDeferred?: boolean; inputSchema?: unknown };

function engine(
  on: On,
  fake: Fake,
  calls: string[],
  tools: Registered[] = [],
): void {
  on("command.register", () => ({ value: { command: "plan-desk" } }));
  on("tool.register", (_, e) => {
    tools.push({
      name: e.name,
      isDeferred: e.isDeferred,
      inputSchema: e.inputSchema,
    });
    return { value: { tool: `mcp__plan-desk__${e.name}` } };
  });
  on("ui.open", () => ({ value: { isPlaced: true } }));
  on("ui.status", () => ({ value: undefined }));
  on("session.start", (_, e) => ({ cwd: e.cwd }));
  on("http.fetch", (_, e) => {
    const method = e.init?.method ?? "GET";
    calls.push(`${method} ${e.url}`);
    const { status, text } = fake(e.url, method);
    return { value: { status, ok: status < 300, headers: {}, text } };
  });
}

const live: Fake = (url, method) => {
  if (url === `${BASE}/api/campaigns`)
    return { status: 200, text: JSON.stringify([CAMPAIGN]) };
  if (url.endsWith("/market-view"))
    return { status: 200, text: JSON.stringify(VIEW) };
  if (url.endsWith("/suggestions") && method === "GET")
    return { status: 200, text: "[]" };
  if (url.endsWith("/suggestions") && method === "POST") {
    return {
      status: 200,
      text: JSON.stringify({
        suggestions: [
          {
            id: "5b0d8f43-0d0b-4bd5-9c55-1e1e5c7b2d10",
            market_plan_id: "a1b2c3d4-0000-4000-8000-000000000001",
            market_code: "SE",
            action: "shift_start",
            flag_date: "2026-05-01",
            new_date: "2026-05-04",
            rationale: "1 May is a public holiday in SE",
            model_deployment: "stub",
            prompt_version: "adapt-v2",
            plan_version: 1,
            created_at: "2026-11-03T15:30:00Z",
            verdict: null,
          },
        ],
        rejected_by_validator: 0,
        rejection_reasons: [],
      }),
    };
  }
  return {
    status: 404,
    text: JSON.stringify({ code: "not_found", message: "no route" }),
  };
};

test(
  "list, show with the pane, and suggest that never accepts",
  { options: { apiBaseUrl: BASE } },
  async ($, on) => {
    const calls: string[] = [];
    engine(on, live, calls);
    await $.session.start({
      cwd: "/",
      surface: "terminal",
      isInteractive: true,
    });

    const list = await $.command.run({ ...RUN, args: "list" });
    expect(list.text).toContain("02b38983  Spring Essentials");

    const show = await $.command.run({ ...RUN, args: "show spring" });
    expect(show.text).toContain(
      "! launch on holiday 1 May 2026: International Workers' Day",
    );
    expect(show.text).toContain("No pending suggestions.");

    for (const surface of ["terminal", "desktop"] as const) {
      const ui = await $.ui.mount({ ...PANE, surface });
      expect(
        (await ui.find({ type: "Text", text: /^Spring Essentials$/ }))?.text,
      ).toBe("Spring Essentials");
      expect(
        (await ui.find({ type: "Text", text: /launch on holiday/ }))?.text,
      ).toBe("! launch on holiday 1 May 2026: International Workers' Day");
      await ui.unmount();
    }

    const suggest = await $.command.run({ ...RUN, args: "suggest spring se" });
    expect(suggest.text).toContain(
      "1 suggestion(s) proposed for SE in Spring Essentials",
    );
    expect(suggest.text).toContain("Nothing was accepted.");
    expect(
      calls.some((c) => c.includes("/accept") || c.includes("/reject")),
    ).toBe(false);
  },
);

test(
  "a failing API answers as a visible line",
  { options: { apiBaseUrl: BASE } },
  async ($, on) => {
    engine(on, () => ({ status: 503, text: "" }), []);
    await $.session.start({
      cwd: "/",
      surface: "terminal",
      isInteractive: true,
    });
    const list = await $.command.run({ ...RUN, args: "list" });
    expect(list.text).toMatch(
      /^plan-desk list failed: .*HTTP 503; .*may be waking up/,
    );
    const bad = await $.command.run({ ...RUN, args: "suggest spring" });
    expect(bad.text).toMatch(/suggest takes a campaign and a market/);
  },
);

test(
  "the model reaches every operation as an undeferred tool, never accept or reject",
  { options: { apiBaseUrl: BASE } },
  async ($, on) => {
    const calls: string[] = [];
    const tools: Registered[] = [];
    engine(on, live, calls, tools);
    await $.session.start({
      cwd: "/",
      surface: "terminal",
      isInteractive: true,
    });

    expect(tools.map((t) => t.name).sort()).toEqual([
      "list_campaigns",
      "show_campaign",
      "suggest_adaptations",
    ]);
    expect(tools.every((t) => t.isDeferred === false)).toBe(true);
    expect(tools.some((t) => /accept|reject|decide/.test(t.name))).toBe(false);

    const list = await $.tool.call({
      tool: "mcp__plan-desk__list_campaigns",
    } as never);
    expect(list.result).toContain("02b38983  Spring Essentials");

    const show = await $.tool.call({
      tool: "mcp__plan-desk__show_campaign",
      campaign: "spring",
    } as never);
    expect(show.result).toContain("! launch on holiday 1 May 2026");

    const suggest = await $.tool.call({
      tool: "mcp__plan-desk__suggest_adaptations",
      campaign: "spring",
      market: "se",
    } as never);
    expect(suggest.result).toContain("1 suggestion(s) proposed for SE");
    expect(suggest.result).toContain("Nothing was accepted.");
    expect(calls.some((c) => /\/accept|\/reject/.test(c))).toBe(false);
  },
);

test(
  "a waking app reaches the model as the client's hint, not a silent timeout",
  { options: { apiBaseUrl: BASE } },
  async ($, on) => {
    engine(on, () => ({ status: 503, text: "" }), []);
    await $.session.start({
      cwd: "/",
      surface: "terminal",
      isInteractive: true,
    });
    const list = await $.tool.call({
      tool: "mcp__plan-desk__list_campaigns",
    } as never);
    expect(list.deny ?? list.text).toMatch(/HTTP 503; .*may be waking up/);
    const bad = await $.tool.call({
      tool: "mcp__plan-desk__suggest_adaptations",
      campaign: "spring",
      market: "Sweden",
    } as never);
    expect(bad.deny ?? bad.text).toMatch(/two-letter code/);
  },
);
