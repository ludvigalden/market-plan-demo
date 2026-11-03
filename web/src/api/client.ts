import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

type Schemas = components["schemas"];
export type Campaign = Schemas["CampaignOut"];
export type Market = Schemas["MarketOut"];
export type MarketView = Schemas["MarketView"];
export type Suggestion = Schemas["SuggestionOut"];
export type AuditEntry = Schemas["AuditEntry"];

export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? "",
  // Resolve fetch per call so the global can be replaced (tests, instrumentation).
  fetch: (request) => globalThis.fetch(request),
});

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Return the body of a successful call, or throw an ApiError carrying the server's message. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (error !== undefined || !response.ok) {
    const message =
      typeof error === "object" && error !== null && "message" in error
        ? String((error as { message: unknown }).message)
        : `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
  return data as T;
}
