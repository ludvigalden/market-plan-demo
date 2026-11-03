/** What the pane draws: plain values, decided by the formatters. */
export type PaneModel = {
  title: string;
  window: string;
  markets: {
    code: string;
    name: string;
    dates: string;
    status: string;
    flags: string[];
    holidaysAvailable: boolean;
  }[];
  pending: string[];
  footer: string;
};

/** What the pane shows: the campaign last read by a command, or why not. */
export type PaneState =
  | { kind: "empty" }
  | { kind: "loading"; label: string }
  | { kind: "ready"; campaignId: string; model: PaneModel }
  | { kind: "error"; message: string };

declare module "claude-code" {
  interface PluginState {
    "plan-desk": { pane: Shaped<PaneState> };
  }
}
