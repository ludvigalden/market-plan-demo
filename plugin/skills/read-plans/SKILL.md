---
name: read-plans
description: Read Market Plan Desk campaigns, market clashes and pending suggestions through the /plan-desk command, and draft local adaptations for a market. Use when the user asks about a campaign's markets, holiday clashes or suggestions.
---

# Plan desk

The `/plan-desk` command reads the Market Plan Desk API configured in the
plugin's `apiBaseUrl` option.

- `/plan-desk list` lists campaigns with a short id, window, budget and
  assigned markets.
- `/plan-desk show <campaign>` prints each market's dates, status and
  holiday clashes, and the suggestions still waiting for a decision. It
  also opens the plan desk pane. `<campaign>` is an id, an id prefix or a
  word of the name.
- `/plan-desk suggest <campaign> <market>` asks the API to draft
  adaptations for one assigned market (a two-letter code such as `SE`) and
  prints them.

Suggestions are proposals only. Accepting or rejecting one is the
planner's decision in the web app; the command has no way to do it, and
you should not try another route. When a user asks you to accept a
suggestion, tell them where to do it.

The app scales to zero when idle, so the first call after a quiet period
can take about 30 seconds. A timeout or an HTTP 502/503 says so; run the
command again.
