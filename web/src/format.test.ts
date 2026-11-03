import { describe, expect, it } from "vitest";
import type { Suggestion } from "./api/client";
import { describeSuggestion, formatDate, pendingFirst } from "./format";

function s(partial: Partial<Suggestion>): Suggestion {
  return {
    id: "1",
    market_plan_id: "p",
    market_code: "SE",
    action: "shift_start",
    flag_date: "2026-05-01",
    new_date: "2026-05-04",
    rationale: "r",
    model_deployment: "stub",
    prompt_version: "adapt-v1",
    created_at: "2026-11-03T00:00:00Z",
    verdict: null,
    plan_version: 1,
    ...partial,
  };
}

describe("format", () => {
  it("formats ISO dates without timezone drift", () => {
    expect(formatDate("2026-05-01")).toBe("1 May 2026");
  });

  it("describes each action", () => {
    expect(describeSuggestion(s({}))).toBe("Move launch to 4 May 2026");
    expect(
      describeSuggestion(s({ action: "shift_end", new_date: "2026-05-29" })),
    ).toBe("Move end to 29 May 2026");
    expect(
      describeSuggestion(s({ action: "note_messaging", new_date: null })),
    ).toBe("Messaging note for 1 May 2026");
  });

  it("lists pending suggestions before decided ones", () => {
    const out = pendingFirst([
      s({ id: "a", verdict: "accepted" }),
      s({ id: "b", market_code: "DE" }),
    ]);
    expect(out.map((x) => x.id)).toEqual(["b", "a"]);
  });
});
