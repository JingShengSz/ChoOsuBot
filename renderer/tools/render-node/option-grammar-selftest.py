"""Local sanity test of the option grammar, without importing AstrBot.

Extracts the three pieces under test from main.py by exec-ing only what they need, so a
mistake here is caught before the plugin reaches the VPS.
"""
import re
import sys

src = open(
    r"D:\DeepSeek Harness\workspace\osu-mania-render\astrbot_plugin_mania_render\main.py",
    encoding="utf-8",
).read()

# Pull the two regexes and the three methods out of the file verbatim.
ns: dict = {"re": re}

m = re.search(r"^SCORE_URL_RE = re\.compile\(.*?\)\n", src, re.S | re.M)
exec(m.group(0), ns)
m = re.search(r"^SCORE_LINK_STRIP_RE = re\.compile\(.*?\)\n", src, re.S | re.M)
exec(m.group(0), ns)

bodies = [
    re.search(rf"^    {name} = \{{.*?\n    \}}\n", src, re.S | re.M).group(0)
    for name in ("BARE_ALIASES", "OPTION_ALIASES")
]
exec("class _C:\n" + "".join(bodies), ns)

meth_bodies = [
    re.search(
        rf"^    @staticmethod\n    def {meth}\(.*?(?=\n    @staticmethod|\n    # )",
        src, re.S | re.M,
    ).group(0)
    for meth in ("_parse_options", "_unknown_options")
]
exec("class _M:\n" + "\n".join(meth_bodies), ns)
ns["ManiaRenderPlugin"] = ns["_M"]
ns["_M"].OPTION_ALIASES = ns["_C"].OPTION_ALIASES
ns["_M"].BARE_ALIASES = ns["_C"].BARE_ALIASES

parse = ns["_M"]._parse_options
unknown = ns["_M"]._unknown_options
strip = ns["SCORE_LINK_STRIP_RE"]
findall = ns["SCORE_URL_RE"].findall

fails = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got={got!r} want={want!r}")
    if not ok:
        fails.append(label)


LINK = "https://osu.ppy.sh/scores/7518410895"

print("1. link stripping leaves nothing that can be misread")
bare = strip.sub(" ", f"小秋这个换boj那个皮肤渲染 {LINK}")
print(f"   stripped -> {bare!r}")
check("no leftover https", "https" in bare, False)
check("no digits left", any(c.isdigit() for c in bare), False)
check("link still found by SCORE_URL_RE", findall(f"x {LINK}"), ["7518410895"])

print()
print("2. options work on the automatic path (text with the link removed)")
cases = [
    (f"{LINK} -s Cho'", {"skin": "Cho'"}),
    (f"{LINK} 皮肤 Cho'", {"skin": "Cho'"}),
    (f"{LINK} -s R Skin", {"skin": "R Skin"}),
    (f"{LINK} -v 25", {"scroll": "25"}),
    (f"{LINK} -d 30", {"bg_dim": "30"}),
    (f"{LINK} -r 720", {"res": "720"}),
    (f"{LINK} -f 120", {"fps": "120"}),
    (f"{LINK} --from 10 --to 40", {"from": "10", "to": "40"}),
    (f"{LINK} -s Cho' -v 25 -d 30 -r 720 -f 120", {
        "skin": "Cho'", "scroll": "25", "bg_dim": "30", "res": "720", "fps": "120"}),
]
for text, want in cases:
    opts, err = parse(strip.sub(" ", text), strict=True)
    check(f"{text!r} -> opts", (opts, err), (want, None))

print()
print("3. no options -> nothing requested (default skin path)")
check("plain link", parse(strip.sub(" ", LINK), strict=True), ({}, None))
# The real symptom message: prose around the link must NOT become a bogus skin name,
# which would turn a previously-working render into a "no such skin" refusal.
check("prose around link (strict) -> default skin",
      parse(strip.sub(" ", f"小秋这个换boj那个皮肤渲染 {LINK}"), strict=True), ({}, None))
check("bare number in prose (strict) is not a bid",
      parse(strip.sub(" ", f"我打了5次 {LINK}"), strict=True), ({}, None))
check("om-style bare word still a skin when not strict",
      parse("渲染一下", strict=False), ({"skin": "渲染一下"}, None))

print()
print("4. errors are surfaced, not swallowed")
check("-s with no value", parse("-s"), ({}, "选项 -s 后面少了值"))
check("unknown flag -z", unknown(f"{LINK} -z 5".replace(LINK, " ")), unknown(" -z 5"))
print(f"   unknown('-z 5') -> {unknown(' -z 5')!r}")
check("known flags are NOT flagged", unknown(" -s Cho' -v 25 --from 1 --to 2"), None)
check("bare alias NOT flagged", unknown(" 皮肤 Cho'"), None)
check("bare skin name NOT flagged", unknown(" Cho'"), None)
check("unknown k=v flagged", unknown(" speed=25") is not None, True)
check("known k=v NOT flagged", unknown(" skin=Cho'"), None)

print()
print("5. om path unchanged: same grammar, same results")
check("om-style bid", parse("2467450 -d 30"), ({"bid": "2467450", "bg_dim": "30"}, None))
check("om-style bare skin", parse("2467450 R Skin"), ({"bid": "2467450", "skin": "R Skin"}, None))

print()
if fails:
    print(f"FAILURES ({len(fails)}): {fails}")
    sys.exit(1)
print("ALL PARSER CHECKS PASSED")
