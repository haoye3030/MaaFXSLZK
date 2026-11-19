
# -*- coding: utf-8 -*-
"""从已存截图中裁 15 个宝箱图标模板（96x96），并生成对照图。"""
from pathlib import Path
from PIL import Image, ImageDraw

SRC = Path(r"E:/DSH/MaaFX/tmp/nav_out")
OUT = Path(r"E:/DSH/MaaFX/MaaFXSLZK/assets/resource/image/warehouse")
DBG = Path(r"E:/DSH/MaaFX/MaaFXSLZK/tmp/_probe")
OUT.mkdir(parents=True, exist_ok=True); DBG.mkdir(parents=True, exist_ok=True)

# 实测网格（145/170/140/155/126 同状态）：
# 卡间空隙 x = 374-382,521-528,668-675,814-821,961-968,1107-1111,右侧 ~1250
# 卡片内部：236..373, 383..520, 529..667, 676..813, 822..960, 969..1106, 1112..1250
COLS_TOP = [304, 451, 598, 744, 891, 1037, 1181]   # 列中心（卡片内部中点）
ROWS_TOP = [200, 355, 510, 665]                    # 行中心（145 状态：label top 123/278/433/588 + 77）
ROWS_S146 = [238, 393, 548]                        # 146 状态：整体下移 38px

T = 96
# (name, screenshot, col(1-7), row_center)
SEL = [
 ("chest_part3",        "145_top.png",  3, ROWS_TOP[0]),
 ("chest_train_begin",  "145_top.png",  2, ROWS_TOP[1]),
 ("chest_train_high",   "145_top.png",  3, ROWS_TOP[1]),
 ("chest_train_ex_begin","145_top.png", 4, ROWS_TOP[1]),
 ("chest_train_ex_mid", "145_top.png",  5, ROWS_TOP[1]),
 ("chest_train_ex_high","145_top.png",  6, ROWS_TOP[1]),
 ("chest_train_ex_top", "145_top.png",  7, ROWS_TOP[1]),
 ("chest_common_box",   "145_top.png",  3, ROWS_TOP[2]),
 ("chest_smuggle_box",  "145_top.png",  2, ROWS_TOP[2]),
 ("chest_gear_high",    "145_top.png",  7, ROWS_TOP[2]),
 ("chest_gun_high",     "146_s1.png",   1, ROWS_S146[0]),
 ("chest_torpedo_high", "146_s1.png",   2, ROWS_S146[0]),
 ("chest_plane_high",   "146_s1.png",   3, ROWS_S146[0]),
 ("chest_aa_high",      "146_s1.png",   4, ROWS_S146[0]),
 ("chest_device_high",  "146_s1.png",   5, ROWS_S146[0]),
]
imgs = {}
tiles = []
for (name, shot, col, cy) in SEL:
    if shot not in imgs:
        imgs[shot] = Image.open(SRC/shot).convert("RGB")
    cx = COLS_TOP[col-1]
    box = (cx-T//2, cy-T//2, cx+T//2, cy+T//2)
    crop = imgs[shot].crop(box)
    crop.save(OUT/f"{name}.png")
    tiles.append((name, shot, col, cx, cy, crop))
    print(f"{name:22s} {shot:14s} col{col} center=({cx},{cy}) box={box}")

# 对照图：15 个模板 5x3，放大 2x
SC=2; pw,ph = T*SC, T*SC+18
sheet = Image.new("RGB",(pw*5, ph*3),(30,30,30)); d=ImageDraw.Draw(sheet)
for i,(name,shot,col,cx,cy,crop) in enumerate(tiles):
    x=(i%5)*pw; y=(i//5)*ph
    sheet.paste(crop.resize((T*SC,T*SC),Image.LANCZOS),(x,y+18))
    d.text((x+3,y+4),f"{i+1}.{name}",fill=(255,255,120))
    d.rectangle([x,y+18,x+T*SC-1,y+18+T*SC-1],outline=(255,80,80))
sheet.save(DBG/"_tpl_contact.png")

# 全网格对照：145 三行 x 7 列 + 146 一行 x 7 列
grid_sheet = Image.new("RGB",(7*T*2, 4*(T*2+16)),(25,25,25))
dg = ImageDraw.Draw(grid_sheet)
for r in range(3):
    for c in range(7):
        crop = imgs["145_top.png"].crop((COLS_TOP[c]-T//2, ROWS_TOP[r]-T//2, COLS_TOP[c]+T//2, ROWS_TOP[r]+T//2))
        x=c*T*2; y=r*(T*2+16)
        grid_sheet.paste(crop.resize((T*2,T*2),Image.LANCZOS),(x,y+16))
        dg.text((x+3,y+2),f"145 r{r+1}c{c+1}",fill=(255,255,120))
for c in range(7):
    crop = imgs["146_s1.png"].crop((COLS_TOP[c]-T//2, ROWS_S146[0]-T//2, COLS_TOP[c]+T//2, ROWS_S146[0]+T//2))
    x=c*T*2; y=3*(T*2+16)
    grid_sheet.paste(crop.resize((T*2,T*2),Image.LANCZOS),(x,y+16))
    dg.text((x+3,y+2),f"146 r1c{c+1}",fill=(120,255,160))
grid_sheet.save(DBG/"_grid_contact.png")
print("saved contact sheets", (DBG/"_tpl_contact.png"), (DBG/"_grid_contact.png"))
