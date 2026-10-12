"""Keep tool replies valid JSON; explicitly report omitted response fields."""

import json


def project(data, fields):
    if not fields:
        return data
    tree = {}
    for field in fields.split(","):
        node = tree
        for part in field.strip().split("."):
            if part:
                node = node.setdefault(part, {})

    def walk(value, spec):
        if not spec:
            return value
        if isinstance(value, list):
            return [walk(v, spec) for v in value]
        if isinstance(value, dict):
            return {
                key: walk(value[key], sub) for key, sub in spec.items() if key in value
            }
        return value

    return walk(data, tree)


def render(
    data, *, operation_id="", source="", cached=False, fields="", max_chars=24000
):
    # Paging metadata survives projection and output-size limiting.
    paging = {
        k: data[k]
        for k in ("cursor_string", "cursor", "total", "search")
        if isinstance(data, dict) and k in data
    }
    data = project(data, fields)
    omitted = []
    budget = [max_chars - 2500]

    def trim(value, path="data", depth=0):
        if budget[0] < 100 or depth > 12:
            omitted.append(path)
            return None
        if isinstance(value, dict):
            result = {}
            for k, v in value.items():
                if budget[0] < 100:
                    omitted.append(path + ".*")
                    break
                budget[0] -= len(k) + 5
                result[k] = trim(v, path + "." + k, depth + 1)
            return result
        if isinstance(value, list):
            result = []
            for i, v in enumerate(value):
                if i >= 50 or budget[0] < 100:
                    omitted.append(f"{path}[{i}:]")
                    break
                result.append(trim(v, f"{path}[{i}]", depth + 1))
            return result
        if isinstance(value, str) and len(value) > 1500:
            omitted.append(path)
            value = value[:1500] + "…"
        budget[0] -= len(json.dumps(value, ensure_ascii=False)) + 2
        return value

    paging_data = trim(paging, "paging") if paging else None
    envelope = {
        "ok": True,
        "operation_id": operation_id,
        "source": source,
        "cached": cached,
        "data": trim(data),
    }
    if paging:
        envelope["paging"] = paging_data
    envelope.update(truncated=bool(omitted), omitted_paths=omitted[:20])
    if omitted:
        envelope["hint"] = (
            "输出已缩减；用 fields 选择字段，或用接口的 limit/offset/cursor_string 翻页。不要把当前数据当作全部记录。"
        )
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
