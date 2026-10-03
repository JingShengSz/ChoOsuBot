import pathlib, re
p = pathlib.Path(r"D:\Documents\qwen-agent\af6bz3jmdg\default\osu-icons\make_icons.py")
s = p.read_text(encoding="utf-8")
pairs = [("mod_1","mod_hd"),("mod_2","mod_dt"),("mod_3","mod_hr"),("mod_4","mod_fl"),
         ("mod_5","mod_ez"),("mod_6","mod_nf"),("mod_7","mod_ht"),("mod_8","mod_so")]
n = 0
for old, new in pairs:
    pat = '("%s",' % old
    if pat in s:
        s = s.replace(pat, '("%s",' % new); n += 1
p.write_text(s, encoding="utf-8")
print("patched entries:", n)
