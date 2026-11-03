import type { Suggestion } from "./api/client";

const dateFmt = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return dateFmt.format(new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)));
}

export function formatEur(amount: string): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "EUR",
  }).format(Number(amount));
}

const CLASH_LABEL: Record<string, string> = {
  launch_on_holiday: "Launch on holiday",
  end_on_holiday: "End on holiday",
  holiday_in_window: "Holiday in window",
};

export function clashLabel(kind: string): string {
  return CLASH_LABEL[kind] ?? kind;
}

/** One-line, human-readable summary of what accepting a suggestion would do. */
export function describeSuggestion(s: Suggestion): string {
  switch (s.action) {
    case "shift_start":
      return `Move launch to ${s.new_date ? formatDate(s.new_date) : "?"}`;
    case "shift_end":
      return `Move end to ${s.new_date ? formatDate(s.new_date) : "?"}`;
    case "note_messaging":
      return `Messaging note for ${s.flag_date ? formatDate(s.flag_date) : "the window"}`;
    case "no_change":
      return "No change";
  }
}

export function pendingFirst(list: Suggestion[]): Suggestion[] {
  return [...list].sort((a, b) => {
    const pa = a.verdict ? 1 : 0;
    const pb = b.verdict ? 1 : 0;
    if (pa !== pb) return pa - pb;
    return (
      a.market_code.localeCompare(b.market_code) ||
      (a.flag_date ?? "").localeCompare(b.flag_date ?? "")
    );
  });
}
