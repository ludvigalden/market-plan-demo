// The three operations the mod offers, shared by the /plan-desk command
// and the model's tools so the two cannot drift apart. Each takes the
// typed client and answers with the text shown, or throws.

import type { PaneModel } from "../types";
import { ApiError, type Campaign, type Client } from "./client.ts";
import {
  formatCampaignList,
  formatPaneText,
  formatSuggestResult,
  isUuid,
  paneModel,
  pickCampaign,
} from "./format.ts";

export function detailOf(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

/** One campaign by id, id prefix or a word of its name. */
export async function resolveCampaign(
  api: Client,
  query: string,
): Promise<Campaign> {
  if (isUuid(query)) {
    return api("get", "/api/campaigns/{campaign_id}", {
      path: { campaign_id: query },
    });
  }
  const picked = pickCampaign(query, await api("get", "/api/campaigns", {}));
  if ("error" in picked) throw new Error(picked.error);
  return picked.campaign;
}

export async function listCampaigns(api: Client): Promise<string> {
  return formatCampaignList(await api("get", "/api/campaigns", {}));
}

export type Shown = { campaignId: string; model: PaneModel; text: string };

export async function showCampaign(api: Client, query: string): Promise<Shown> {
  const campaign = await resolveCampaign(api, query);
  const path = { campaign_id: campaign.id };
  const [view, suggestions] = await Promise.all([
    api("get", "/api/campaigns/{campaign_id}/market-view", { path }),
    api("get", "/api/campaigns/{campaign_id}/suggestions", { path }),
  ]);
  const model = paneModel(view, suggestions);
  return {
    campaignId: campaign.id,
    model,
    text: formatPaneText(model, campaign.id),
  };
}

/** Drafts adaptations for one assigned market. Never accepts any. */
export async function suggestAdaptations(
  api: Client,
  query: string,
  market: string,
): Promise<string> {
  const campaign = await resolveCampaign(api, query);
  if (!campaign.market_codes.includes(market)) {
    const assigned =
      campaign.market_codes.length === 0
        ? "none"
        : campaign.market_codes.join(", ");
    throw new Error(
      `${market} is not assigned to ${campaign.name} (assigned: ${assigned})`,
    );
  }
  const result = await api("post", "/api/campaigns/{campaign_id}/suggestions", {
    path: { campaign_id: campaign.id },
    body: { market_codes: [market] },
  });
  return formatSuggestResult(result, market, campaign);
}
