"""Align Pillow text slots with the revised score-card PSD layout."""
import json
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "layer_mapping.json"
doc = json.loads(path.read_text(encoding="utf-8"))
layers = doc["textLayers"]
by_name = {layer["name"]: layer for layer in layers}

def move(name, dx=0, dy=0):
    layer = by_name[name]
    layer["x"] += dx
    layer["y"] += dy
    layer["ink"] = [layer["ink"][0]+dx, layer["ink"][1]+dy,
                    layer["ink"][2]+dx, layer["ink"][3]+dy]

if "length" not in by_name:
    move("beatmap_title", 42, 0)
    move("player_name", -66, -95)
    by_name["player_name"]["justify"] = "left"
    by_name["player_name"]["freeWidthPx"] = 365
    move("rank_change", -72, -9)
    by_name["rank_change"]["justify"] = "left"
    move("total_pp", 139, -143)
    move("_deco_total_pp_label", 140, -147)
    by_name["bpm"]["freeWidthPx"] = 150
    for name,dx,example in (("length",203,"2:45"),("keys",401,"4K")):
        item = dict(by_name["bpm"])
        item["name"] = name
        item["x"] += dx
        item["ink"] = [item["ink"][0]+dx,item["ink"][1],
                       item["ink"][2]+dx,item["ink"][3]]
        item["example"] = example
        item["freeWidthPx"] = 150
        layers.append(item)
    for raster in doc.get("rasterLayers", []):
        if raster.get("name") == "player_avatar":
            raster.update(x=720,y=75,note="圆角方形头像")
if "score_suffix" not in by_name:
    item = dict(by_name["score"])
    item.update(name="score_suffix",sizePx=28,color="#8C97A9",x=870,y=516,
                example=".979",ink=[870,516,927,543],freeWidthPx=100,maxChars=5)
    layers.append(item)
path.write_text(json.dumps(doc,ensure_ascii=False,indent=1)+"\n",encoding="utf-8")
