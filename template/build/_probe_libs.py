import importlib, sys
print("python:", sys.version.split()[0], sys.executable)
print()
for m in ["PIL", "cairosvg", "numpy", "aiohttp", "httpx", "requests", "win32com", "svgwrite", "matplotlib"]:
    try:
        mod = importlib.import_module(m)
        print("  %-14s OK   %s" % (m, getattr(mod, "__version__", "?")))
    except Exception as e:
        print("  %-14s --   %s" % (m, type(e).__name__))
print()
try:
    from PIL import ImageFont
    import glob, os
    pats = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\Inter*.ttf"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\Montserrat*.ttf"),
        r"C:\Windows\Fonts\Inter*.ttf",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\JetBrainsMono*.ttf"),
    ]
    for p in pats:
        hits = glob.glob(p)
        print("  %s -> %d" % (p.replace(os.path.expandvars("%LOCALAPPDATA%"), "%LAD%"), len(hits)))
        for h in hits[:6]:
            print("      ", os.path.basename(h))
except Exception as e:
    print("font probe failed:", e)
