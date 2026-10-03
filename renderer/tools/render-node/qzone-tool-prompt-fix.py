import re, shutil, time, sys

F = "/opt/astrbot/data/plugins/astrbot_plugin_qzone_tools/main.py"
src = open(F, encoding="utf-8").read()

OLD = '''            inject_parts.append("""[重要工具使用规范] 你需要调用功能时，必须遵循以下步骤：
1. 首先使用 search_wyc_tools 工具，传入简短关键词（例如"邮箱"、"禁言"、"发说说"、"记忆"、"状态"、"资料"），不要使用完整问句！
2. 如果 search_wyc_tools 未找到，再尝试 call_wyc_tools 查看全部可用工具列表。
3. 确定工具名称后，使用 run_wyc_tool 并传入工具名称和 JSON 格式的参数。
禁止直接猜测工具名称，必须通过搜索获取。""")'''

NEW = '''            # Scoped to THIS plugin's namespace. It used to be an unconditional blanket
            # rule -- "禁止直接猜测工具名称，必须通过搜索获取" -- that covered every tool in
            # the request. `search_wyc_tools`/`call_wyc_tools` only know this plugin's own
            # tools, so an agent told to find ALL tools through them concludes that any tool
            # missing from that list (e.g. render_mania_video) does not exist, and falls back
            # to shell/Python. The tools outside this namespace are already in the schema and
            # are meant to be called directly.
            inject_parts.append("""[QZoneTools 工具使用规范] 调用本插件的功能（QQ空间、群管理、消息发送、记忆、AI语音、历史消息、群文件等）时，请遵循以下步骤：
1. 首先使用 search_wyc_tools 工具，传入简短关键词（例如"邮箱"、"禁言"、"发说说"、"记忆"、"状态"、"资料"），不要使用完整问句！
2. 如果 search_wyc_tools 未找到，再尝试 call_wyc_tools 查看本插件的全部可用工具列表。
3. 确定工具名称后，使用 run_wyc_tool 并传入工具名称和 JSON 格式的参数。

注意：search_wyc_tools / call_wyc_tools 只覆盖本插件的工具。请求中其他工具（例如 render_mania_video、osu_*、analyze_* 等）不在这个列表里 —— 它们已经直接提供给你，请直接按名字调用，不要用 search_wyc_tools 去查找，也不要因为在那里搜不到就认为它不存在。""")'''

if OLD not in src:
    print("!! the exact block was NOT found -- aborting, nothing written")
    sys.exit(1)

backup = F + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(F, backup)
print("backup:", backup)

src = src.replace(OLD, NEW, 1)
open(F, "w", encoding="utf-8").write(src)
print("written:", F)
print("new length:", len(src))

# verify
chk = open(F, encoding="utf-8").read()
print("old blanket ban still present:", "禁止直接猜测工具名称" in chk)
print("scoped header present       :", "[QZoneTools 工具使用规范]" in chk)
print("render_mania_video mentioned:", "render_mania_video" in chk)
import py_compile
py_compile.compile(F, doraise=True)
print("py_compile: OK")
