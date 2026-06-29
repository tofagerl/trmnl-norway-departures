#!/usr/bin/env python3
"""Regenerate testing/markup-test.html as a static, offline preview.

Renders the four TRMNL view sizes from a sample payload in the *original*
cloud-function contract:

    departures = { "<line>": { "<destination> - <platform>": [ {expected, ...} ] } }

The <div class="view view--*"> wrapper added here is supplied by the TRMNL
platform in production — the .liquid source files must NOT include it.

Run from anywhere:  python testing/gen.py
"""

import html
import os

ICON = "https://trmnl.com/images/plugins/trmnl--render.svg"

# Sample payload matching the original cloud function's output shape.
SAMPLE = {
    "departures": {
        "5": {
            "Ringen via Storo - 1": [{"expected": "14:58.00"}, {"expected": "15:12.00"}],
            "Vestli - 1": [{"expected": "14:55.29"}, {"expected": "15:09.06"}],
            "Ringen via Tøyen - 2": [{"expected": "15:04.06"}, {"expected": "15:18.00"}],
            "Sognsvann via Tøyen - 2": [{"expected": "15:00.00"}, {"expected": "15:15.05"}],
        },
        "L2": {
            "Oslo S - 3": [{"expected": "14:53.00"}, {"expected": "15:08.00"}],
        },
        "17": {
            "Sinsen-Grefsen st. - D": [
                {"expected": "14:55.57"},
                {"expected": "15:02.30"},
                {"expected": "15:11.48"},
                {"expected": "15:20.00"},
            ],
            "Rikshospitalet - E": [{"expected": "14:58.00"}, {"expected": "15:08.00"}],
        },
        "31": {
            "Snarøya - C": [{"expected": "14:57.00"}, {"expected": "15:05.00"}],
            "Tonsenhagen - F": [{"expected": "15:01.00"}, {"expected": "15:13.00"}],
        },
    },
    "last_updated": "13:48",
    "minutes_to_fetch": "30",
    "name": "Carl Berners plass",
}


def esc(value):
    return html.escape(str(value))


def oslo_banner(departures):
    """Soonest departure to Oslo S across all lines — mirrors shared.liquid."""
    best = None
    for line, destinations in departures.items():
        for dest_key, times in destinations.items():
            if "Oslo S" not in dest_key.split(" - ")[0]:
                continue
            t = times[0]["expected"].split(".")[0]
            if best is None or t < best[0]:
                best = (t, line, dest_key.split(" - ")[0])
    if best is None:
        return ""
    time, line, dest = best
    return (
        f'<div class="item"><div class="meta"><span class="index">{esc(line)}</span></div>'
        f'<div class="content"><span class="label label--small">{esc(dest)}</span>'
        f'<span class="value value--large value--tnums">{esc(time)}</span></div></div>'
    )


def column(departures, max_cols, time_limit=None, dest_limit=None):
    out = [f'<div class="column" data-overflow-max-cols="{max_cols}" data-overflow-counter="true">']
    out.append(oslo_banner(departures))
    for line, destinations in departures.items():
        out.append(f'<div class="item"><div class="meta"><span class="index">{esc(line)}</span></div><div class="content">')
        for i, (dest_key, times) in enumerate(destinations.items()):
            if dest_limit and i >= dest_limit:
                break
            parts = dest_key.split(" - ")
            platform = f" ({esc(parts[1])})" if len(parts) > 1 and not dest_limit else ""
            out.append(f'<span class="title title--small" data-clamp="1">{esc(parts[0])}{platform}</span>')
            out.append('<div class="flex flex--row flex--wrap gap--small">')
            shown = times[:time_limit] if time_limit else times
            for time in shown:
                out.append(f'<span class="label label--small label--underline">{esc(time["expected"].split(".")[0])}</span>')
            out.append('</div>')
        out.append('</div></div>')
    out.append('</div>')
    return "\n".join(out)


def view(cls, inner, station, instance):
    return f'''  <div class="screen">
    <div class="view {cls}">
      <div class="layout"><div class="columns">{inner}</div></div>
      <div class="title_bar">
        <img class="image" src="{ICON}">
        <span class="title" data-clamp="1">{station}</span>
        <span class="instance">{instance}</span>
      </div>
    </div>
  </div>'''


def main():
    p = SAMPLE
    station = esc(p["name"])
    subtitle = f'Next {p["minutes_to_fetch"]} min · {p["last_updated"]}'
    deps = p["departures"]

    views = "\n".join([
        view("view--full", column(deps, 3), station, subtitle),
        view("view--half_vertical", column(deps, 1, time_limit=4), station, subtitle),
        view("view--half_horizontal", column(deps, 4, time_limit=3), station, subtitle),
        view("view--quadrant", column(deps, 1, time_limit=2, dest_limit=1), station, p["last_updated"]),
    ])

    doc = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Norway departures — TRMNL preview</title>
  <link rel="stylesheet" href="https://usetrmnl.com/css/latest/plugins.css">
  <script src="https://usetrmnl.com/js/latest/plugins.js"></script>
</head>
<!-- Generated by testing/gen.py. Do not hand-edit. -->
<body class="environment trmnl">
{views}
</body>
</html>
'''
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "markup-test.html")
    with open(out_path, "w") as fh:
        fh.write(doc)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
