"""Prepare browser detail-card data from a saved analysis JSON.

Run with the workspace Python runtime. This reads no network data and does not
modify the analyser or score-card modules.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = Path(sys.argv[1])
OUT = Path(sys.argv[2]) / "data.js"


def reduced_curve(graph: dict, count: int = 720) -> dict:
    times = graph.get("times") or []
    values = graph.get("values") or []
    if not times or len(times) != len(values):
        return {"times": [], "values": [], "sourcePoints": len(times)}
    # Retain local extremes within each horizontal pixel group, rather than
    # taking every Nth point and potentially losing short difficulty spikes.
    pairs = []
    for start in range(0, len(times), max(1, len(times) // count)):
        section = list(zip(times[start:start + max(1, len(times) // count)],
                           values[start:start + max(1, len(times) // count)]))
        if not section:
            continue
        first, last = section[0], section[-1]
        lo, hi = min(section, key=lambda p: p[1]), max(section, key=lambda p: p[1])
        for pair in sorted({first, lo, hi, last}):
            if not pairs or pair != pairs[-1]:
                pairs.append(pair)
    pairs.sort(key=lambda p: p[0])
    return {"times": [p[0] for p in pairs], "values": [round(p[1], 4) for p in pairs],
            "sourcePoints": len(times)}


def density(starts: list[int]) -> dict:
    """Fixed 1 s, non-overlapping bins from first object; each object once."""
    ordered = sorted(starts)
    if not ordered:
        return {"counts": [], "peak": 0, "mean": 0}
    bins = [0] * (int((ordered[-1] - ordered[0]) // 1000) + 1)
    for t in ordered:
        bins[int((t - ordered[0]) // 1000)] += 1
    return {"counts": bins, "peak": max(bins),
            "mean": len(ordered) / max(1, (ordered[-1] - ordered[0]) / 1000),
            "firstMs": ordered[0], "lastMs": ordered[-1], "unit": "notes/s"}


raw = json.loads(SOURCE.read_text(encoding="utf-8"))
segment_file = SOURCE.with_name("pattern_segments.json")
pattern_segments = (json.loads(segment_file.read_text(encoding="utf-8"))
                    if segment_file.is_file() else None)
parsed = raw["parsed"]
algorithms = raw["algorithms"]
sunny = algorithms["Sunny"]
summary = {
    "beatmapId": raw["beatmapId"], "sourceId": raw.get("sourceId"), "conditions": raw["conditions"],
    "vibroDetection": raw.get("vibroDetection"),
    "metadata": parsed["metaData"],
    "parsed": {key: value for key, value in parsed.items()
               if key not in {"columns", "noteStarts", "noteEnds", "noteTypes", "objectIntervals"}},
    "objectStats": {
        "columns": len(parsed["columns"]), "noteStarts": len(parsed["noteStarts"]),
        "noteEnds": len(parsed["noteEnds"]), "noteTypes": len(parsed["noteTypes"]),
        "objectIntervals": len(parsed["objectIntervals"]),
        "noteTypeCounts": {str(kind): parsed["noteTypes"].count(kind)
                           for kind in sorted(set(parsed["noteTypes"]))},
        "firstStartMs": min(parsed["noteStarts"]),
        "lastStartMs": max(parsed["noteStarts"]),
        "lastEndMs": max(parsed["noteEnds"]),
    },
    "density": density(parsed["noteStarts"]),
    "patternSegments": pattern_segments,
    "algorithms": {
        name: {
            "actualEstimatorAlgorithm": result["actualEstimatorAlgorithm"],
            "rework": {key: value for key, value in result["rework"].items() if key != "graph"},
            "curve": reduced_curve(result["rework"].get("graph") or {}),
            "sunnyStar": result["sunnyStar"],
        } for name, result in algorithms.items()
    },
    "companella": raw["companella"],
    "sunnyWindow": {key: value for key, value in sunny["sunnyWindow"].items() if key != "graph"},
    "sunnyWindowCurve": reduced_curve(sunny["sunnyWindow"].get("graph") or {}),
    "sixKConst": sunny["sixKConst"], "vibro": sunny["vibro"],
    "ppMetrics": sunny["ppMetrics"], "maxReworkPp": raw["maxReworkPp"],
    "patternReport": sunny["patternReport"],
    "patternTopFiveClusters": sunny["patternTopFiveClusters"],
    "ettResult": sunny["ettResult"], "interludeStar": sunny["interludeStar"],
    "diagnostics": {key: sunny[key] for key in
                    ("patternError", "ettError", "ettErrorCode", "interludeError",
                     "companellaEttError", "errors")},
    "companellaEttResult": None if sunny["companellaEttResult"] is None else
                           {key: value for key, value in sunny["companellaEttResult"].items()
                            if key != "graph"},
}
OUT.write_text("window.BEATMAP_DETAILS = " + json.dumps(summary, ensure_ascii=False,
                                                            separators=(",", ":")) + ";\n",
               encoding="utf-8")
print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")
print("Density peak", summary["density"]["peak"], "mean", round(summary["density"]["mean"], 2))
