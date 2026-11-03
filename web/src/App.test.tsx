import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

afterEach(() => vi.unstubAllGlobals());

describe("App", () => {
  it("renders the campaigns list from the API", async () => {
    const campaigns = [
      {
        id: "c1",
        name: "Spring Essentials",
        window_start: "2026-05-01",
        window_end: "2026-05-31",
        global_budget_eur: "250000.00",
        market_codes: ["DE", "SE"],
        created_at: "2026-11-03T00:00:00Z",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify(campaigns), {
            headers: { "content-type": "application/json" },
          }),
      ),
    );
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("link", { name: "Spring Essentials" }),
    ).toBeInTheDocument();
    expect(screen.getByText("DE, SE")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: "Campaigns" }),
    ).toBeInTheDocument();
  });
});
