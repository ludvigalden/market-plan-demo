// A typed client over the host's fetch. Paths, parameters, bodies and
// responses come from the generated contract types; the transport is
// injected, so the hooks pass `$.http.fetch` and tests pass a fake.

import type { components, paths } from "../generated/schema.d.ts";

export type Schemas = components["schemas"];
export type Campaign = Schemas["CampaignOut"];
export type MarketView = Schemas["MarketView"];
export type Suggestion = Schemas["SuggestionOut"];
export type SuggestResult = Schemas["SuggestResult"];

type Method = "get" | "post" | "put" | "patch" | "delete";

/** The methods a path serves (the generated `never` slots dropped). */
type MethodOf<P extends keyof paths> = {
  [M in Method]: paths[P][M] extends undefined ? never : M;
}[Method];

type Op<P extends keyof paths, M extends Method> = NonNullable<paths[P][M]>;

type PathInit<O> = O extends { parameters: { path: infer PP } }
  ? { path: PP }
  : { path?: undefined };

type BodyInit<O> = O extends { requestBody?: never }
  ? { body?: undefined }
  : O extends { requestBody: { content: { "application/json": infer B } } }
    ? { body: B }
    : O extends { requestBody?: { content: { "application/json": infer B } } }
      ? { body?: B }
      : { body?: undefined };

type Json<R> = R extends { content: { "application/json": infer T } }
  ? T
  : undefined;

/** The success body of an operation: its 200, else 201, else 204. */
export type Ok<O> = O extends { responses: infer R }
  ? R extends { 200: infer S }
    ? Json<S>
    : R extends { 201: infer S }
      ? Json<S>
      : undefined
  : never;

export type Init<O> = PathInit<O> & BodyInit<O>;

/** The slice of `$.http.fetch` the client uses. */
export type Fetcher = (
  url: string,
  init?: { method?: string; headers?: Record<string, string>; body?: string },
) => Promise<{ status: number; ok: boolean; text: string }>;

/** Schedules `fn` after `ms`; the hooks pass `$.clock.after`. */
export type After = (ms: number, fn: () => void) => { cancel: () => void };

export type ClientDeps = {
  baseUrl: string;
  fetch: Fetcher;
  after: After;
  timeoutMs?: number;
};

/** Long enough for a scale-from-zero start, which takes about 35 s. */
export const DEFAULT_TIMEOUT_MS = 60_000;

/** Why a call failed, in the words the commands show. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly kind: "timeout" | "unreachable" | "waking" | "http" | "decode",
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const WAKING_HINT =
  "the app scales to zero when idle and may be waking up; run the command again in about 30 s";

function fillPath(template: string, params: unknown): string {
  return template.replace(/\{([^}]+)\}/g, (_, name: string) => {
    const value = (params as Record<string, unknown> | undefined)?.[name];
    if (value === undefined) throw new Error(`missing path parameter ${name}`);
    return encodeURIComponent(String(value));
  });
}

function errorMessage(status: number, text: string): string {
  try {
    const body = JSON.parse(text) as Partial<Schemas["ErrorBody"]>;
    if (typeof body.message === "string") {
      return body.code === undefined
        ? body.message
        : `${body.message} (${body.code})`;
    }
  } catch {
    // not an error body; fall through to the status line
  }
  return `HTTP ${status}`;
}

export type Client = <P extends keyof paths, M extends MethodOf<P>>(
  method: M,
  path: P,
  init: Init<Op<P, M>>,
) => Promise<Ok<Op<P, M>>>;

export function createClient(deps: ClientDeps): Client {
  const base = deps.baseUrl.replace(/\/+$/, "");
  const timeoutMs = deps.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  return async (method, path, init) => {
    const url = base + fillPath(path, (init as { path?: unknown }).path);
    const body = (init as { body?: unknown }).body;
    const request = deps.fetch(url, {
      method: method.toUpperCase(),
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    let timer: { cancel: () => void } | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = deps.after(timeoutMs, () =>
        reject(
          new ApiError(
            `no response from ${base} within ${Math.round(timeoutMs / 1000)} s; ${WAKING_HINT}`,
            "timeout",
          ),
        ),
      );
    });
    let response: Awaited<ReturnType<Fetcher>>;
    try {
      response = await Promise.race([request, timeout]);
    } catch (error) {
      if (error instanceof ApiError) throw error;
      const detail = error instanceof Error ? error.message : String(error);
      throw new ApiError(`could not reach ${base}: ${detail}`, "unreachable");
    } finally {
      timer?.cancel();
    }
    if (
      response.status === 502 ||
      response.status === 503 ||
      response.status === 504
    ) {
      throw new ApiError(
        `${base} answered HTTP ${response.status}; ${WAKING_HINT}`,
        "waking",
        response.status,
      );
    }
    if (!response.ok) {
      throw new ApiError(
        errorMessage(response.status, response.text),
        "http",
        response.status,
      );
    }
    if (response.text === "")
      return undefined as Ok<Op<typeof path, typeof method>>;
    try {
      return JSON.parse(response.text) as Ok<Op<typeof path, typeof method>>;
    } catch {
      throw new ApiError(
        `${base} answered HTTP ${response.status} with a body that is not JSON`,
        "decode",
        response.status,
      );
    }
  };
}
