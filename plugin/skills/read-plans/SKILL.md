---
name: read-plans
description: Read Market Plan Desk campaigns, market clashes and pending suggestions through the plan-desk tools, and draft local adaptations for a market. Use when the user asks about a campaign's markets, holiday clashes or suggestions.
---

# Plan desk

The `plan-desk` plugin registers three tools. Call the tool; do not curl
the API yourself, and do not read the plugin's sources to find the URL.
The tools carry the configured API base URL, the contract types and the
wake-up handling already.

- `mcp__plan-desk__list_campaigns` — campaigns with a short id, window,
  budget and assigned markets.
- `mcp__plan-desk__show_campaign` — one campaign's markets, holiday
  clashes and pending suggestions. The `campaign` argument accepts an id,
  an id prefix or a word of the name.
- `mcp__plan-desk__suggest_adaptations` — drafts adaptations for one
  assigned market (a two-letter code such as `SE`) and returns them.

Suggestions are proposals only. Accepting or rejecting one is the
planner's decision in the web app; no tool can do it, and you should not
try another route. When a user asks you to accept a suggestion, tell them
where to do it.

The API scales to zero when idle, so the first call can take about 30
seconds. A tool result saying the app may be waking up means: call the
tool again shortly.

The `/plan-desk` slash command runs the same three operations for a
person and opens the plan desk pane; you do not need it.
