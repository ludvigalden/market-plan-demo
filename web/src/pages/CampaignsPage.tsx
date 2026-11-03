import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Campaign, unwrap } from "../api/client";
import { ErrorMessage, Loading } from "../components/Status";
import { formatDate, formatEur } from "../format";

export function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setCampaigns(await unwrap(api.GET("/api/campaigns")));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <h1>Campaigns</h1>
      <p className="lead">
        Plan a campaign once, assign local markets, and review AI-proposed local
        adaptations before anything changes.
      </p>
      <ErrorMessage error={error} />
      {campaigns === null ? (
        <Loading label="Loading campaigns…" />
      ) : campaigns.length === 0 ? (
        <p className="muted">No campaigns yet. Create one below.</p>
      ) : (
        <table>
          <caption className="visually-hidden">Campaigns</caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Window</th>
              <th scope="col">Global budget</th>
              <th scope="col">Markets</th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((c) => (
              <tr key={c.id}>
                <td>
                  <Link to={`/campaigns/${c.id}`}>{c.name}</Link>
                </td>
                <td>
                  {formatDate(c.window_start)} – {formatDate(c.window_end)}
                </td>
                <td>{formatEur(c.global_budget_eur)}</td>
                <td>{c.market_codes.join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <CreateCampaignForm />
    </>
  );
}

function CreateCampaignForm() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const created = await unwrap(
        api.POST("/api/campaigns", {
          body: {
            name: String(form.get("name")),
            window_start: String(form.get("window_start")),
            window_end: String(form.get("window_end")),
            global_budget_eur: String(form.get("global_budget_eur")),
          },
        }),
      );
      navigate(`/campaigns/${created.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="create-heading" className="card">
      <h2 id="create-heading">New campaign</h2>
      <form onSubmit={onSubmit} className="form-grid">
        <label>
          Name
          <input
            name="name"
            required
            maxLength={120}
            defaultValue="Spring Essentials"
          />
        </label>
        <label>
          Window start
          <input
            name="window_start"
            type="date"
            required
            defaultValue="2026-05-01"
          />
        </label>
        <label>
          Window end
          <input
            name="window_end"
            type="date"
            required
            defaultValue="2026-05-31"
          />
        </label>
        <label>
          Global budget (EUR)
          <input
            name="global_budget_eur"
            type="number"
            min="1"
            step="0.01"
            required
            defaultValue="250000"
          />
        </label>
        <div className="form-actions">
          <button type="submit" disabled={busy}>
            {busy ? "Creating…" : "Create campaign"}
          </button>
        </div>
      </form>
      <ErrorMessage error={error} />
    </section>
  );
}
