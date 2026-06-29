# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A [TRMNL](https://trmnl.com) plugin that shows Norwegian public-transport departures (Entur/Ruter) on an e-ink display. Two independent halves:

1. **Cloud function** (`src/cloud-function/`) — Python GCP HTTP function. Queries Entur's GraphQL journey-planner, groups departures by line/destination/platform, returns JSON.
2. **TRMNL markup** (`src/trmnl/`) — Liquid templates that render that JSON across the four screen sizes.

## Fork caveat (important)

This is a fork of the **original author's** plugin. The live TRMNL plugin polls the original author's **deployed** cloud function at `https://europe-north1-trmnl-451212.cloudfunctions.net/function-1` (GCP project `trmnl-451212`, not ours). We do **not** deploy `src/cloud-function/trmnl.py` — it's kept here as the contract reference for the markup. Treat the cloud function as read-only source-of-truth for the JSON shape; changes to it won't affect the live plugin.

## Data flow

```
TRMNL platform  --polls-->  cloud function URL (settings.yml polling_url)
cloud function  --GraphQL-->  api.entur.io  -->  grouped JSON
TRMNL  --merge vars-->  shared.liquid then one size template  -->  e-ink render
```

The polling URL requires `secret=public` and interpolates the custom fields (`stop_id`, `exclude_platforms`, `minutes_to_fetch`) defined in `settings.yml`.

## JSON contract (cloud function → Liquid)

```
departures        { "<line>": { "<destination> - <platform>": [ { expected, schedule, type } ] } }
name              station name
last_updated      "HH:MM"
minutes_to_fetch  departure window size
```

Note: the payload also has a `num_departures-excludes` key — the hyphen makes it unreachable in Liquid (parsed as subtraction), so don't rely on it.

## Markup conventions

- `shared.liquid` runs before every view (sets `line_count`, `subtitle`). The four size files are `full`, `half_horizontal`, `half_vertical`, `quadrant`.
- Templates must **NOT** include the `<div class="view view--*">` wrapper — the TRMNL platform adds it in production. `testing/gen.py` adds it only for the offline preview.
- Use the TRMNL CSS framework classes (`item`, `meta`, `content`, `title`, `label`, `title_bar`, etc.). Invoke the `trmnl` skill for framework/markup work; use the `mcp__trmnl__*` tools to read/write live markup.

## Commands

```bash
python testing/gen.py                  # regenerate testing/markup-test.html offline preview (open in browser)
python src/cloud-function/trmnl.py     # run cloud function locally in VERBOSE mode (see __main__ for example stops)
```

No build system, lint, or test suite. `jupyter/trmnl.ipynb` is the original author's scratch notebook.
