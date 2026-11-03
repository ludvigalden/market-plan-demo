// The tools the model calls, as `mcp__plan-desk__<name>`: their specs
// and the pure check of each call's input. Accept and reject are absent
// on purpose; those decisions stay with the planner in the web app.

export const PLUGIN = "plan-desk";

export const TOOL = {
  list: "list_campaigns",
  show: "show_campaign",
  suggest: "suggest_adaptations",
} as const;

export function fullName(name: string): string {
  return `mcp__${PLUGIN}__${name}`;
}

const CAMPAIGN_PROP = {
  type: "string",
  description:
    "The campaign: its id, an id prefix of at least 4 characters, or a word of its name",
  minLength: 1,
};

const WAKE_NOTE =
  "The API scales to zero when idle: the first call can take about 30 s, and a result saying the app may be waking up means call again shortly.";

export const TOOL_SPECS = [
  {
    name: TOOL.list,
    description: `List Market Plan Desk campaigns: short id, name, window, global budget in EUR and assigned markets. Read-only. ${WAKE_NOTE}`,
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
    isDeferred: false,
  },
  {
    name: TOOL.show,
    description: `Show one campaign: each market's dates and status, its public-holiday clashes, and the AI suggestions still waiting for a planner's decision. Read-only. ${WAKE_NOTE}`,
    inputSchema: {
      type: "object",
      properties: { campaign: CAMPAIGN_PROP },
      required: ["campaign"],
      additionalProperties: false,
    },
    isDeferred: false,
  },
  {
    name: TOOL.suggest,
    description: `Draft local adaptations for one market of a campaign and return them. The drafts are stored as pending proposals; nothing is accepted, and there is no tool to accept or reject: a planner decides in the web app. ${WAKE_NOTE}`,
    inputSchema: {
      type: "object",
      properties: {
        campaign: CAMPAIGN_PROP,
        market: {
          type: "string",
          description:
            "A two-letter market code assigned to the campaign, such as SE",
          pattern: "^[A-Za-z]{2}$",
        },
      },
      required: ["campaign", "market"],
      additionalProperties: false,
    },
    isDeferred: false,
  },
] as const;

export type ToolRequest =
  | { kind: "list" }
  | { kind: "show"; campaign: string }
  | { kind: "suggest"; campaign: string; market: string }
  | { kind: "error"; message: string };

function stringArg(
  input: Record<string, unknown>,
  key: string,
): string | undefined {
  const value = input[key];
  return typeof value === "string" && value.trim() !== ""
    ? value.trim()
    : undefined;
}

/** Check a tool call's arguments; the engine passes them beside `tool`. */
export function toolRequest(
  name: string,
  input: Record<string, unknown>,
): ToolRequest {
  if (name === fullName(TOOL.list)) return { kind: "list" };
  const campaign = stringArg(input, "campaign");
  if (campaign === undefined) {
    return {
      kind: "error",
      message: "campaign is required: an id, id prefix or name word",
    };
  }
  if (name === fullName(TOOL.show)) return { kind: "show", campaign };
  if (name === fullName(TOOL.suggest)) {
    const market = stringArg(input, "market");
    if (market === undefined || !/^[A-Za-z]{2}$/.test(market)) {
      return {
        kind: "error",
        message: "market must be a two-letter code such as SE",
      };
    }
    return { kind: "suggest", campaign, market: market.toUpperCase() };
  }
  return { kind: "error", message: `unknown tool ${name}` };
}
