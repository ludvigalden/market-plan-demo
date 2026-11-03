// The plan-desk mod: three tools the model calls, a /plan-desk command
// over the same actions, and a side pane. It reads and proposes only;
// accept and reject stay in the web app. Failures answer visibly.

import { atom, read, update } from "claude-code";
import type { EngineInterface, Register } from "claude-code";

import type { PaneState } from "../types";
import {
  detailOf,
  listCampaigns,
  showCampaign,
  suggestAdaptations,
} from "./actions.ts";
import { type Client, createClient } from "./client.ts";
import { COMMAND, errorText, parseArgs, USAGE } from "./format.ts";
import { fullName, TOOL, TOOL_SPECS, toolRequest } from "./tools.ts";

const PANE = "plan-desk";
const DEFAULT_BASE_URL =
  "https://mpd-app.graysky-09e0f216.swedencentral.azurecontainerapps.io";

const pane = atom(
  { plugin: "plan-desk", key: "pane" } as const,
  { kind: "empty" },
  { shape: "pane-1" },
);

function clientFor($: EngineInterface, baseUrl: string): Client {
  return createClient({
    baseUrl,
    fetch: (url, init) => $.http.fetch(url, init),
    after: (ms, fn) => $.clock.after(ms, fn),
  });
}

/** Register the model's tools; a refused one is named, never skipped. */
async function registerTools($: EngineInterface): Promise<string[]> {
  const refused: string[] = [];
  for (const spec of TOOL_SPECS) {
    try {
      await $.tool.register({ ...spec, inputSchema: { ...spec.inputSchema } });
    } catch (error) {
      refused.push(`${spec.name}: ${detailOf(error)}`);
    }
  }
  return refused;
}

/** Show a campaign and keep it for the pane. */
async function showIntoPane(
  $: EngineInterface,
  api: Client,
  query: string,
): Promise<string> {
  await update($, pane, (): PaneState => ({ kind: "loading", label: query }));
  try {
    const shown = await showCampaign(api, query);
    await update($, pane, (): PaneState => ({
      kind: "ready",
      campaignId: shown.campaignId,
      model: shown.model,
    }));
    return shown.text;
  } catch (error) {
    const message = errorText("show", detailOf(error));
    await update($, pane, (): PaneState => ({ kind: "error", message }));
    throw error;
  }
}

export const register: Register = (on, options) => {
  const configured = options["apiBaseUrl"];
  const baseUrl =
    typeof configured === "string" && configured.trim() !== ""
      ? configured.trim()
      : DEFAULT_BASE_URL;

  on("session.start", async ($, e, next) => {
    const refused = await registerTools($);
    if (refused.length > 0) {
      $.ui.toast(`plan-desk: tools not registered: ${refused.join("; ")}`);
    }
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

  for (const name of [TOOL.list, TOOL.show, TOOL.suggest]) {
    on("tool.call", { tool: fullName(name) }, async ($, e) => {
      const request = toolRequest(e.tool, e as Record<string, unknown>);
      const api = clientFor($, baseUrl);
      try {
        if (request.kind === "error") return { deny: request.message };
        if (request.kind === "list")
          return { result: await listCampaigns(api) };
        if (request.kind === "show") {
          return { result: await showIntoPane($, api, request.campaign) };
        }
        return {
          result: await suggestAdaptations(
            api,
            request.campaign,
            request.market,
          ),
        };
      } catch (error) {
        return { deny: errorText(name, detailOf(error)) };
      }
    }).catch((_$, _e, next) => ({
      deny: errorText(
        name,
        next.error.kind === "timeout"
          ? "ran out of time; the app may be waking up, call again in about 30 s"
          : (next.error.message ?? "it stopped without a message"),
      ),
    }));
  }

  on("command.run", { command: COMMAND }, async ($, e) => {
    const parsed = parseArgs(e.args);
    if (parsed.kind === "error") return { text: parsed.message };
    const api = clientFor($, baseUrl);
    try {
      $.ui.status(`plan-desk: ${parsed.kind} via ${baseUrl}`);
      if (parsed.kind === "list") return { text: await listCampaigns(api) };
      if (parsed.kind === "show") {
        const opened = await $.ui.open({ id: PANE, title: "Plan desk" });
        const text = await showIntoPane($, api, parsed.campaign);
        const where = opened.isPlaced
          ? "Shown in the plan desk pane."
          : "The plan desk pane is open but not drawn here.";
        return { text: `${text}\n${where}` };
      }
      return {
        text: await suggestAdaptations(api, parsed.campaign, parsed.market),
      };
    } catch (error) {
      return { text: errorText(parsed.kind, detailOf(error)) };
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
