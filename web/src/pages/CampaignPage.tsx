import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  type AuditEntry,
  api,
  type Market,
  type MarketView,
  type Suggestion,
  unwrap,
} from "../api/client";
import { ErrorMessage, Loading } from "../components/Status";
import {
  clashLabel,
  describeSuggestion,
  formatDate,
  formatEur,
  pendingFirst,
} from "../format";

export function CampaignPage() {
  const { id = "" } = useParams();
  const [view, setView] = useState<MarketView | null>(null);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const path = { params: { path: { campaign_id: id } } };

  const reload = useCallback(async () => {
    const p = { params: { path: { campaign_id: id } } };
    try {
      const [v, m, s, a] = await Promise.all([
        unwrap(api.GET("/api/campaigns/{campaign_id}/market-view", p)),
        unwrap(api.GET("/api/markets")),
        unwrap(api.GET("/api/campaigns/{campaign_id}/suggestions", p)),
        unwrap(api.GET("/api/campaigns/{campaign_id}/audit", p)),
      ]);
      setView(v);
      setMarkets(m);
      setSuggestions(s);
      setAudit(a);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function run(action: () => Promise<string | null>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNotice(await action());
    } catch (e) {
      const msg = (e as Error).message;
      setError(
        e instanceof ApiError && e.status === 409 ? `Conflict: ${msg}` : msg,
      );
    } finally {
      await reload();
      setBusy(false);
    }
  }

  async function onAssign(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const codes = new FormData(e.currentTarget).getAll("market").map(String);
    await run(async () => {
      if (codes.length === 0) throw new Error("Select at least one market.");
      await unwrap(
        api.PUT("/api/campaigns/{campaign_id}/markets", {
          ...path,
          body: { market_codes: codes },
        }),
      );
      return `Markets set: ${codes.join(", ")}.`;
    });
  }

  async function onSuggest() {
    await run(async () => {
      const r = await unwrap(
        api.POST("/api/campaigns/{campaign_id}/suggestions", path),
      );
      const dropped = r.rejected_by_validator
        ? ` ${r.rejected_by_validator} dropped by the validator.`
        : "";
      return `${r.suggestions.length} suggestion(s) drafted.${dropped}`;
    });
  }

  async function decide(s: Suggestion, verdict: "accept" | "reject") {
    await run(async () => {
      const route =
        verdict === "accept"
          ? "/api/suggestions/{suggestion_id}/accept"
          : "/api/suggestions/{suggestion_id}/reject";
      await unwrap(
        api.POST(route, {
          params: { path: { suggestion_id: s.id } },
          body: { expected_plan_version: s.plan_version },
        }),
      );
      return `${verdict === "accept" ? "Accepted" : "Rejected"}: ${s.market_code} – ${describeSuggestion(s)}.`;
    });
  }

  if (!view) {
    return (
      <>
        <ErrorMessage error={error} />
        {!error && <Loading label="Loading campaign…" />}
      </>
    );
  }

  const c = view.campaign;
  const assigned = new Set(c.market_codes);
  const pending = suggestions.filter((s) => !s.verdict).length;

  return (
    <>
      <p>
        <Link to="/">← All campaigns</Link>
      </p>
      <h1>{c.name}</h1>
      <p className="lead">
        {formatDate(c.window_start)} – {formatDate(c.window_end)} · global
        budget {formatEur(c.global_budget_eur)}
      </p>
      <div aria-live="polite" className="live">
        {notice && <p className="notice">{notice}</p>}
      </div>
      <ErrorMessage error={error} />

      <section aria-labelledby="markets-heading" className="card">
        <h2 id="markets-heading">Markets</h2>
        <form onSubmit={onAssign}>
          <fieldset>
            <legend>Assign local markets</legend>
            <div className="checks">
              {markets.map((m) => (
                <label key={m.code} className="check">
                  <input
                    type="checkbox"
                    name="market"
                    value={m.code}
                    defaultChecked={assigned.has(m.code)}
                  />
                  {m.name} ({m.code})
                </label>
              ))}
            </div>
          </fieldset>
          <button type="submit" disabled={busy}>
            Save markets
          </button>
        </form>
      </section>

      <section aria-labelledby="view-heading">
        <h2 id="view-heading">Market view</h2>
        {view.markets.length === 0 ? (
          <p className="muted">No markets assigned yet.</p>
        ) : (
          <div className="market-grid">
            {view.markets.map((row) => (
              <article
                key={row.plan.id}
                className="card market"
                aria-labelledby={`m-${row.plan.market_code}`}
              >
                <h3 id={`m-${row.plan.market_code}`}>
                  {row.plan.market_name}{" "}
                  <span className="code">{row.plan.market_code}</span>
                </h3>
                <dl>
                  <dt>Dates</dt>
                  <dd data-testid={`dates-${row.plan.market_code}`}>
                    {formatDate(row.plan.start_date)} –{" "}
                    {formatDate(row.plan.end_date)}
                  </dd>
                  <dt>Budget</dt>
                  <dd>
                    {formatEur(row.plan.budget_eur)} (
                    {(Number(row.plan.budget_share) * 100).toFixed(1)} %)
                  </dd>
                  <dt>Status</dt>
                  <dd>
                    {row.plan.status} · v{row.plan.version}
                  </dd>
                </dl>
                {!row.holidays_available ? (
                  <p className="warn">
                    Holidays unavailable right now; try again shortly.
                  </p>
                ) : row.clashes.length === 0 ? (
                  <p className="muted">
                    No public holidays in the plan window.
                  </p>
                ) : (
                  <ul
                    className="flags"
                    aria-label={`Holiday flags for ${row.plan.market_name}`}
                  >
                    {row.clashes.map((cl) => (
                      <li key={cl.date} className={`flag flag-${cl.kind}`}>
                        <strong>{clashLabel(cl.kind)}</strong>{" "}
                        {formatDate(cl.date)}: {cl.holiday_name}
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="sugg-heading" className="card">
        <h2 id="sugg-heading">AI suggestions</h2>
        <p className="muted">
          Suggestions are proposals only. They are checked against the holiday
          data before they are shown, and nothing changes until you accept one.
        </p>
        <button
          type="button"
          onClick={onSuggest}
          disabled={busy || view.markets.length === 0}
        >
          Draft local adaptations
        </button>
        {suggestions.length === 0 ? (
          <p className="muted">No suggestions yet.</p>
        ) : (
          <>
            <p>{pending} pending.</p>
            <ul className="suggestions">
              {pendingFirst(suggestions).map((s) => (
                <li
                  key={s.id}
                  className={`suggestion${s.verdict ? " decided" : ""}`}
                >
                  <div>
                    <strong>
                      {s.market_code}: {describeSuggestion(s)}
                    </strong>
                    <p>{s.rationale}</p>
                    <p className="meta">
                      {s.model_deployment} · {s.prompt_version}
                    </p>
                  </div>
                  {s.verdict ? (
                    <span className={`badge badge-${s.verdict}`}>
                      {s.verdict}
                    </span>
                  ) : (
                    <div className="actions">
                      <button
                        type="button"
                        onClick={() => decide(s, "accept")}
                        disabled={busy}
                        aria-label={`Accept: ${s.market_code} ${describeSuggestion(s)}`}
                      >
                        Accept
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => decide(s, "reject")}
                        disabled={busy}
                        aria-label={`Reject: ${s.market_code} ${describeSuggestion(s)}`}
                      >
                        Reject
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section aria-labelledby="audit-heading" className="card">
        <h2 id="audit-heading">Audit log</h2>
        {audit.length === 0 ? (
          <p className="muted">No decisions yet.</p>
        ) : (
          <table>
            <caption className="visually-hidden">
              Decisions on AI suggestions
            </caption>
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Market</th>
                <th scope="col">Action</th>
                <th scope="col">Verdict</th>
                <th scope="col">By</th>
                <th scope="col">Model / prompt</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.decision_id}>
                  <td>{new Date(a.decided_at).toLocaleString("en-GB")}</td>
                  <td>{a.market_code}</td>
                  <td>{a.action}</td>
                  <td>{a.verdict}</td>
                  <td>{a.decided_by}</td>
                  <td>
                    {a.model_deployment} / {a.prompt_version}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
