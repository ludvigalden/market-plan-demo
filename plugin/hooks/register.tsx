// The plan-desk mod: a slash command over the Market Plan Desk API and a
// side pane for the campaign it last read. It reads and proposes only;
// accept and reject stay in the web app. Failures answer visibly.

import { atom, read, update } from "claude-code";
import type { EngineInterface, Register } from "claude-code";

import type { PaneState } from "../types";
import {
  ApiError,
  type Campaign,
  type Client,
  createClient,
} from "./client.ts";
import {
  COMMAND,
  errorText,
  formatCampaignList,
  formatPaneText,
  formatSuggestResult,
  isUuid,
  paneModel,
  parseArgs,
  pickCampaign,
  USAGE,
} from "./format.ts";

const PANE = "plan-desk";
const DEFAULT_BASE_URL =
  "https://mpd-app.graysky-09e0f216.swedencentral.azurecontainerapps.io";

const pane = atom(
  { plugin: "plan-desk", key: "pane" } as const,
  { kind: "empty" },
  {
    shape: "pane-1",
  },
);

function detailOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

function clientFor($: EngineInterface, baseUrl: string): Client {
  return createClient({
    baseUrl,
    fetch: (url, init) => $.http.fetch(url, init),
    after: (ms, fn) => $.clock.after(ms, fn),
  });
}

async function resolveCampaign(api: Client, query: string): Promise<Campaign> {
  if (isUuid(query)) {
    return api("get", "/api/campaigns/{campaign_id}", {
      path: { campaign_id: query },
    });
  }
  const picked = pickCampaign(query, await api("get", "/api/campaigns", {}));
  if ("error" in picked) throw new Error(picked.error);
  return picked.campaign;
}

export const register: Register = (on, options) => {
  const configured = options["apiBaseUrl"];
  const baseUrl =
    typeof configured === "string" && configured.trim() !== ""
      ? configured.trim()
      : DEFAULT_BASE_URL;

  on("session.start", async ($, e, next) => {
    try {
      await $.command.register({
        name: COMMAND,
        description:
          "Read Market Plan Desk campaigns and propose local adaptations",
        argumentHint: "list | show <campaign> | suggest <campaign> <market>",
      });
    } catch (error) {
      $.ui.toast(
        `plan-desk: /${COMMAND} was not registered: ${detailOf(error)}`,
      );
    }
    return next(e);
  });

  on("command.run", { command: COMMAND }, async ($, e) => {
    const parsed = parseArgs(e.args);
    const api = clientFor($, baseUrl);

    if (parsed.kind === "error") return { text: parsed.message };

    if (parsed.kind === "list") {
      try {
        $.ui.status(`plan-desk: reading campaigns from ${baseUrl}`);
        return {
          text: formatCampaignList(await api("get", "/api/campaigns", {})),
        };
      } catch (error) {
        return { text: errorText("list", detailOf(error)) };
      } finally {
        $.ui.status(undefined);
      }
    }

    if (parsed.kind === "show") {
      try {
        $.ui.status(`plan-desk: reading ${parsed.campaign}`);
        await update($, pane, (): PaneState => ({
          kind: "loading",
          label: parsed.campaign,
        }));
        const opened = await $.ui.open({ id: PANE, title: "Plan desk" });
        const campaign = await resolveCampaign(api, parsed.campaign);
        const path = { campaign_id: campaign.id };
        const [view, suggestions] = await Promise.all([
          api("get", "/api/campaigns/{campaign_id}/market-view", { path }),
          api("get", "/api/campaigns/{campaign_id}/suggestions", { path }),
        ]);
        const model = paneModel(view, suggestions);
        await update($, pane, (): PaneState => ({
          kind: "ready",
          campaignId: campaign.id,
          model,
        }));
        const where = opened.isPlaced
          ? "Shown in the plan desk pane."
          : "The plan desk pane is open but not drawn here.";
        return { text: `${formatPaneText(model, campaign.id)}\n${where}` };
      } catch (error) {
        const message = errorText("show", detailOf(error));
        await update($, pane, (): PaneState => ({ kind: "error", message }));
        return { text: message };
      } finally {
        $.ui.status(undefined);
      }
    }

    try {
      $.ui.status(`plan-desk: drafting suggestions for ${parsed.market}`);
      const campaign = await resolveCampaign(api, parsed.campaign);
      if (!campaign.market_codes.includes(parsed.market)) {
        const assigned =
          campaign.market_codes.length === 0
            ? "none"
            : campaign.market_codes.join(", ");
        return {
          text: errorText(
            "suggest",
            `${parsed.market} is not assigned to ${campaign.name} (assigned: ${assigned})`,
          ),
        };
      }
      const result = await api(
        "post",
        "/api/campaigns/{campaign_id}/suggestions",
        {
          path: { campaign_id: campaign.id },
          body: { market_codes: [parsed.market] },
        },
      );
      return { text: formatSuggestResult(result, parsed.market, campaign) };
    } catch (error) {
      return { text: errorText("suggest", detailOf(error)) };
    } finally {
      $.ui.status(undefined);
    }
  }).catch((_$, _e, next) => ({
    text: errorText(
      "command",
      next.error.kind === "timeout"
        ? "ran out of time; the app may be waking up, run it again in about 30 s"
        : (next.error.message ?? "it stopped without a message"),
    ),
  }));

  on("ui.render", { component: "Pane", requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e);
    const state: PaneState = await read($, pane);
    if (state.kind === "empty") {
      return (
        <Text dimColor>{`Run /${COMMAND} show <campaign>. ${USAGE}`}</Text>
      );
    }
    if (state.kind === "loading") {
      return <Text dimColor>{`Reading ${state.label}…`}</Text>;
    }
    if (state.kind === "error") {
      return <Text color="red">{state.message}</Text>;
    }
    const { model } = state;
    return (
      <Box flexDirection="column">
        <Text bold>{model.title}</Text>
        <Text dimColor>{model.window}</Text>
        {model.markets.map((m) => (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>{`${m.code} ${m.name}`}</Text>
            <Text>{`${m.dates} · ${m.status}`}</Text>
            {!m.holidaysAvailable && <Text dimColor>holidays unavailable</Text>}
            {m.flags.map((flag) => (
              <Text color="yellow">{`! ${flag}`}</Text>
            ))}
          </Box>
        ))}
        <Box flexDirection="column" marginTop={1}>
          <Text bold>{`Pending suggestions (${model.pending.length})`}</Text>
          {model.pending.length === 0 && <Text dimColor>none</Text>}
          {model.pending.map((line) => (
            <Text>{line}</Text>
          ))}
        </Box>
        <Box marginTop={1}>
          <Text dimColor>{model.footer}</Text>
        </Box>
      </Box>
    );
  });
};
