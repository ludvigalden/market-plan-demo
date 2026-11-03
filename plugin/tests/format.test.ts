import { describe, expect, test } from "claude-code/testing";

import { createClient } from "../hooks/client.ts";
import {
  formatCampaignList,
  formatPaneText,
  formatSuggestResult,
  paneModel,
  parseArgs,
  pickCampaign,
} from "../hooks/format.ts";
import type { Campaign, MarketView, Suggestion } from "../hooks/client.ts";

const CAMPAIGN: Campaign = {
  id: "02b38983-5893-4593-83b3-36bab625b6b1",
  name: "Spring Essentials",
  window_start: "2026-05-01",
  window_end: "2026-05-31",
  global_budget_eur: "250000.00",
  market_codes: ["SE", "JP"],
  created_at: "2026-11-03T15:24:40Z",
};

const SUGGESTION: Suggestion = {
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
};

const VIEW: MarketView = {
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
        budget_share: "0.5000",
        budget_eur: "125000.00",
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

describe("parseArgs", () => {
  test("reads the three subcommands", () => {
    expect(parseArgs("")).toEqual({ kind: "list" });
    expect(parseArgs(" list ")).toEqual({ kind: "list" });
    expect(parseArgs("show spring")).toEqual({
      kind: "show",
      campaign: "spring",
    });
    expect(parseArgs("show spring\nshell noise here")).toEqual({
      kind: "show",
      campaign: "spring",
    });
    expect(parseArgs("suggest 02b38983 se")).toEqual({
      kind: "suggest",
      campaign: "02b38983",
      market: "SE",
    });
  });

  test("refuses malformed input with a usage line", () => {
    for (const bad of [
      "show",
      "suggest spring",
      "suggest spring SWE",
      "accept x",
      "list x",
    ]) {
      const parsed = parseArgs(bad);
      expect(parsed.kind).toBe("error");
    }
    const unknown = parseArgs("accept 1");
    expect(unknown.kind === "error" && unknown.message).toMatch(
      /unknown subcommand "accept"/,
    );
  });
});

describe("pickCampaign", () => {
  const other: Campaign = {
    ...CAMPAIGN,
    id: "ffff0000-0000-4000-8000-000000000000",
    name: "Autumn Basics",
  };

  test("matches an id prefix or a name word, and names ambiguity", () => {
    expect(pickCampaign("02b3", [CAMPAIGN, other])).toEqual({
      campaign: CAMPAIGN,
    });
    expect(pickCampaign("autumn", [CAMPAIGN, other])).toEqual({
      campaign: other,
    });
    expect(pickCampaign("nothing", [CAMPAIGN])).toEqual({
      error: 'no campaign matches "nothing"; run /plan-desk list',
    });
    const both = pickCampaign("s", [CAMPAIGN, other]);
    expect("error" in both && both.error).toMatch(/matches 2 campaigns/);
  });
});

describe("formatters", () => {
  test("list, show and suggest text", () => {
    expect(formatCampaignList([CAMPAIGN])).toBe(
      "1 campaign(s):\n02b38983  Spring Essentials  1 May 2026 – 31 May 2026  EUR 250000.00  SE JP",
    );
    const text = formatPaneText(paneModel(VIEW, [SUGGESTION]), CAMPAIGN.id);
    expect(text).toContain("SE Sweden  1 May 2026 – 31 May 2026  draft");
    expect(text).toContain(
      "! launch on holiday 1 May 2026: International Workers' Day",
    );
    expect(text).toContain(
      "SE shift start to 4 May 2026: 1 May is a public holiday in SE",
    );
    const decided = paneModel(VIEW, [{ ...SUGGESTION, verdict: "accepted" }]);
    expect(decided.pending).toEqual([]);
    const proposed = formatSuggestResult(
      {
        suggestions: [SUGGESTION],
        rejected_by_validator: 1,
        rejection_reasons: ["date outside window"],
      },
      "SE",
      CAMPAIGN,
    );
    expect(proposed).toContain(
      "1 suggestion(s) proposed for SE in Spring Essentials",
    );
    expect(proposed).toContain(
      "1 dropped by the validator: date outside window",
    );
    expect(proposed).toContain("Nothing was accepted.");
  });
});

describe("client", () => {
  const never = () => ({ cancel: () => {} });

  test("fills path parameters and decodes JSON", async () => {
    const seen: string[] = [];
    const api = createClient({
      baseUrl: "http://api.test/",
      after: never,
      fetch: async (url, init) => {
        seen.push(`${init?.method} ${url} ${init?.body ?? ""}`);
        return {
          status: 200,
          ok: true,
          text: JSON.stringify({
            suggestions: [],
            rejected_by_validator: 0,
            rejection_reasons: [],
          }),
        };
      },
    });
    const result = await api(
      "post",
      "/api/campaigns/{campaign_id}/suggestions",
      {
        path: { campaign_id: CAMPAIGN.id },
        body: { market_codes: ["SE"] },
      },
    );
    expect(result.suggestions).toEqual([]);
    expect(seen).toEqual([
      `POST http://api.test/api/campaigns/${CAMPAIGN.id}/suggestions {"market_codes":["SE"]}`,
    ]);
  });

  test("surfaces the server message, a waking app and a timeout", async () => {
    const answering = (status: number, text: string) =>
      createClient({
        baseUrl: "http://api.test",
        after: never,
        fetch: async () => ({ status, ok: status < 300, text }),
      });
    await expect(
      answering(
        404,
        JSON.stringify({ code: "not_found", message: "campaign not found" }),
      )("get", "/api/campaigns", {}),
    ).rejects.toThrow("campaign not found (not_found)");
    await expect(
      answering(503, "")("get", "/api/campaigns", {}),
    ).rejects.toThrow(/may be waking up/);

    const timingOut = createClient({
      baseUrl: "http://api.test",
      timeoutMs: 1000,
      after: (_ms, fn) => {
        fn();
        return { cancel: () => {} };
      },
      fetch: () => new Promise(() => {}),
    });
    await expect(timingOut("get", "/api/campaigns", {})).rejects.toThrow(
      /no response from http:\/\/api\.test within 1 s; .*may be waking up/,
    );
  });
});
