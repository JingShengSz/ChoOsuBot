export function f2(v) {
    return Number.isFinite(v) ? v.toFixed(2) : "0.00";
}

export function buildLinePath(points) {
    const len = points.length;
    if (!len) return "";

    const parts = new Array(len * 2 + 2);
    parts[0] = "M";
    parts[1] = f2(points[0][0]);
    parts[2] = f2(points[0][1]);
    let wi = 3;
    for (let i = 1; i < len; i++) {
        parts[wi++] = "L";
        parts[wi++] = f2(points[i][0]);
        parts[wi++] = f2(points[i][1]);
    }
    return parts.join(" ");
}

export function buildFillPath(points, baseY) {
    const len = points.length;
    if (!len) return "";

    const baseYs = f2(baseY);
    const parts = new Array(len * 3 + 8);
    parts[0] = "M";
    parts[1] = f2(points[0][0]);
    parts[2] = baseYs;
    parts[3] = "L";
    parts[4] = f2(points[0][0]);
    parts[5] = f2(points[0][1]);
    let wi = 6;
    for (let i = 1; i < len; i++) {
        parts[wi++] = "L";
        parts[wi++] = f2(points[i][0]);
        parts[wi++] = f2(points[i][1]);
    }
    parts[wi++] = "L";
    parts[wi++] = f2(points[len - 1][0]);
    parts[wi++] = baseYs;
    parts[wi++] = "Z";
    return parts.join(" ");
}

export function normalizeGraphSeries(graphData, resampleIntervalMs) {
    const rawTimes = Array.isArray(graphData?.times) ? graphData.times : [];
    const rawValues = Array.isArray(graphData?.values) ? graphData.values : [];

    const length = Math.max(rawTimes.length, rawValues.length);
    if (length < 2) {
        return null;
    }

    // Pre-allocate for speed
    const times = new Array(length);
    const values = new Array(length);
    let wi = 0;

    let lastTime = Number.NEGATIVE_INFINITY;
    let lastValue = 0;

    // Track min/max in the same pass
    let minY = Number.POSITIVE_INFINITY;
    let maxY = Number.NEGATIVE_INFINITY;

    for (let i = 0; i < length; i += 1) {
        let time = rawTimes.length > 0 ? Number(rawTimes[i]) : i * resampleIntervalMs;
        let value = rawValues.length > 0 ? Number(rawValues[i]) : lastValue;

        if (!Number.isFinite(time)) continue;

        if (!Number.isFinite(value)) {
            value = wi > 0 ? values[wi - 1] : 0;
        }

        if (time <= lastTime) {
            time = lastTime + 1;
        }

        times[wi] = time;
        values[wi] = value;
        if (value < minY) minY = value;
        if (value > maxY) maxY = value;
        lastTime = time;
        lastValue = value;
        wi += 1;
    }

    if (wi < 2) return null;

    // Trim to actual count
    if (wi < length) {
        times.length = wi;
        values.length = wi;
    }

    return { times, values, minYValue: minY, maxYValue: maxY };
}

export function interpolateSeriesValue(times, values, targetTime) {
    if (!times.length || !values.length) {
        return 0;
    }

    if (targetTime <= times[0]) {
        return values[0];
    }
    if (targetTime >= times[times.length - 1]) {
        return values[values.length - 1];
    }

    let lo = 0;
    let hi = times.length - 1;
    while (lo + 1 < hi) {
        const mid = (lo + hi) >> 1;
        if (times[mid] <= targetTime) {
            lo = mid;
        } else {
            hi = mid;
        }
    }

    const x0 = times[lo];
    const x1 = times[hi];
    const y0 = values[lo];
    const y1 = values[hi];
    if (x1 === x0) {
        return y0;
    }

    const t = (targetTime - x0) / (x1 - x0);
    return y0 + t * (y1 - y0);
}
