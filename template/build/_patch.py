import pathlib
SRC = pathlib.Path(r"D:\Documents\qwen-agent\af6bz3jmdg\default\osu-icons\make_icons.py")
DST = pathlib.Path(r"D:\Cho Osu Bot\template\build\make_icons_v2.py")
s = SRC.read_text(encoding="utf-8")

before = s
s = s.replace('("count_miss", "0",   (0xF0, 0x90, 0x90), (0xE4, 0x5B, 0x5B)),',
              '("count_miss", "X",   (0xF0, 0x90, 0x90), (0xE4, 0x5B, 0x5B)),')
print("miss glyph patched:", s != before)

before2 = s
s = s.replace('OUT_DIR = Path(__file__).parent / "script"',
              'OUT_DIR = Path(r"D:\\Cho Osu Bot\\template\\_icons\\out")')
print("outdir patched:", s != before2)

DST.write_text(s, encoding="utf-8")
print("wrote:", DST)
