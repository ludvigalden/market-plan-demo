// Pure pieces of the plan-desk command: argument parsing, campaign
// lookup and the text and pane models. No `$`, no I/O.

import type { PaneModel } from "../types";
import type {
  Campaign,
  MarketView,
  Suggestion,
  SuggestResult,
} from "./client.ts";

export type { PaneModel };

export const COMMAND = "plan-desk";
export const USAGE = `usage: /${COMMAND} list | show <campaign> | suggest <campaign> <market>`;

export type Parsed =
  | { kind: "list" }
  | { kind: "show"; campaign: string }
  | { kind: "suggest"; campaign: string; market: string }
  | { kind: "error"; message: string };

/**
 * Parse the text typed after `/plan-desk`. Only its first line counts:
 * a headless prompt can carry trailing lines that are not arguments.
 */
export function parseArgs(args: string): Parsed {
  const line = (args.split(/\r?\n/, 1)[0] ?? "").trim();
  const parsed = parseWords(line);
  return parsed.kind === "error"
    ? { kind: "error", message: `${parsed.message} (got "${line}")` }
    : parsed;
}

function parseWords(args: string): Parsed {
  const words = args
    .trim()
    .split(/\s+/)
    .filter((word) => word !== "");
  const [verb, ...rest] = words;
  switch (verb?.toLowerCase()) {
    case undefined:
    case "list":
      return rest.length === 0
        ? { kind: "list" }
        : { kind: "error", message: `list takes no arguments; ${USAGE}` };
    case "show":
      return rest.length === 1 && rest[0] !== undefined
        ? { kind: "show", campaign: rest[0] }
        : { kind: "error", message: `show takes one campaign; ${USAGE}` };
    case "suggest": {
      const [campaign, market] = rest;
      if (rest.length !== 2 || campaign === undefined || market === undefined) {
        return {
          kind: "error",
          message: `suggest takes a campaign and a market; ${USAGE}`,
        };
      }
      if (!/^[A-Za-z]{2}$/.test(market)) {
        return {
          kind: "error",
          message: `market must be a two-letter code such as SE, got "${market}"`,
        };
      }
      return { kind: "suggest", campaign, market: market.toUpperCase() };
    }
    default:
      return {
        kind: "error",
        message: `unknown subcommand "${verb}"; ${USAGE}`,
      };
  }
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID.test(value);
}

/**
 * Find one campaign by id prefix or by a word of its name. Returns the
 * campaign or the reason none was chosen.
 */
export function pickCampaign(
  query: string,
  campaigns: readonly Campaign[],
): { campaign: Campaign } | { error: string } {
  const needle = query.toLowerCase();
  const byId = campaigns.filter((c) => c.id.toLowerCase().startsWith(needle));
  const matches =
    byId.length > 0
      ? byId
      : campaigns.filter((c) => c.name.toLowerCase().includes(needle));
  const [only, ...others] = matches;
  if (only === undefined) {
    return { error: `no campaign matches "${query}"; run /${COMMAND} list` };
  }
  if (others.length > 0) {
    const names = matches.map((c) => `${shortId(c.id)} ${c.name}`).join(", ");
    return {
      error: `"${query}" matches ${matches.length} campaigns: ${names}`,
    };
  }
  return { campaign: only };
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/** `2026-05-01` as `1 May 2026`; anything else unchanged. */
export function formatDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  const month = match ? MONTHS[Number(match[2]) - 1] : undefined;
  if (!match || month === undefined) return iso;
  return `${Number(match[3])} ${month} ${match[1]}`;
}

function range(start: string, end: string): string {
  return `${formatDate(start)} – ${formatDate(end)}`;
}

const CLASH_LABEL: Record<string, string> = {
  launch_on_holiday: "launch on holiday",
  end_on_holiday: "end on holiday",
  holiday_in_window: "holiday in window",
};

export function clashLabel(kind: string): string {
  return CLASH_LABEL[kind] ?? kind.replace(/_/g, " ");
}

/** One line per suggestion: market, action, the date it moves to, why. */
export function suggestionLine(s: Suggestion): string {
  const action = s.action.replace(/_/g, " ");
  const to = s.new_date === null ? "" : ` to ${formatDate(s.new_date)}`;
  return `${s.market_code} ${action}${to}: ${s.rationale}`;
}

export function formatCampaignList(campaigns: readonly Campaign[]): string {
  if (campaigns.length === 0)
    return "No campaigns yet. Create one in the web app.";
  const lines = campaigns.map((c) => {
    const markets =
      c.market_codes.length === 0 ? "no markets" : c.market_codes.join(" ");
    return `${shortId(c.id)}  ${c.name}  ${range(c.window_start, c.window_end)}  EUR ${c.global_budget_eur}  ${markets}`;
  });
  return [`${campaigns.length} campaign(s):`, ...lines].join("\n");
}

export function pending(suggestions: readonly Suggestion[]): Suggestion[] {
  return suggestions.filter(
    (s) => s.verdict === null || s.verdict === undefined,
  );
}

export function paneModel(
  view: MarketView,
  suggestions: readonly Suggestion[],
): PaneModel {
  const open = pending(suggestions);
  return {
    title: view.campaign.name,
    window: `${range(view.campaign.window_start, view.campaign.window_end)} · EUR ${view.campaign.global_budget_eur}`,
    markets: view.markets.map((row) => ({
      code: row.plan.market_code,
      name: row.plan.market_name,
      dates: range(row.plan.start_date, row.plan.end_date),
      status: row.plan.status,
      flags: row.clashes.map(
        (c) => `${clashLabel(c.kind)} ${formatDate(c.date)}: ${c.holiday_name}`,
      ),
      holidaysAvailable: row.holidays_available,
    })),
    pending: open.map(suggestionLine),
    footer: "Accept or reject suggestions in the web app.",
  };
}

/** The same model as transcript text, for `show`. */
export function formatPaneText(model: PaneModel, id: string): string {
  const lines = [`${model.title} (${shortId(id)})`, model.window, ""];
  if (model.markets.length === 0) lines.push("No markets assigned.");
  for (const m of model.markets) {
    lines.push(`${m.code} ${m.name}  ${m.dates}  ${m.status}`);
    if (!m.holidaysAvailable) lines.push("  holidays unavailable");
    for (const flag of m.flags) lines.push(`  ! ${flag}`);
  }
  lines.push("");
  if (model.pending.length === 0) {
    lines.push("No pending suggestions.");
  } else {
    lines.push(`${model.pending.length} pending suggestion(s):`);
    for (const line of model.pending) lines.push(`  ${line}`);
  }
  lines.push(model.footer);
  return lines.join("\n");
}

export function formatSuggestResult(
  result: SuggestResult,
  market: string,
  campaign: Campaign,
): string {
  const head = `${result.suggestions.length} suggestion(s) proposed for ${market} in ${campaign.name}`;
  const lines = [head];
  if (result.suggestions.length === 0) {
    lines.push("No clash needs a change.");
  }
  for (const s of result.suggestions) {
    lines.push(
      `  ${suggestionLine(s)}  [${s.model_deployment} · ${s.prompt_version}]`,
    );
  }
  if (result.rejected_by_validator > 0) {
    lines.push(
      `${result.rejected_by_validator} dropped by the validator: ${result.rejection_reasons.join("; ")}`,
    );
  }
  lines.push("Nothing was accepted. Review and decide in the web app.");
  return lines.join("\n");
}

export function errorText(subcommand: string, detail: string): string {
  return `plan-desk ${subcommand} failed: ${detail}`;
}
