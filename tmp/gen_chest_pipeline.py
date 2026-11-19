# -*- coding: utf-8 -*-
r"""生成 assets/resource/pipeline/chest.json（仓库开箱）。

幂等：每次运行整份重建。素材 = assets/resource/image/warehouse/chest_*.png（96x96 图标裁切，
滑动 NCC 校验：自命中 >=0.93，家族兄弟箱干扰 0.95~0.99 —— 兄弟箱都在目标名单内，误配只影响开箱顺序）。

状态机（ChestRoot 为根，每轮识别一个状态）：
    奖励浮层(点击继续) > 信息面板(使用数量) > 15 个目标箱卡片 > 滚动 > 退出
装备库容满时点「打开」不会弹奖励浮层，面板仍留着 → ChestOpenFail 关面板并退出。
"""
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "assets" / "resource" / "pipeline" / "chest.json"

# (节点后缀, 模板文件, 阈值) —— 阈值按滑动 NCC 实测调整：part3 对 II级部件箱干扰 0.960，故抬到 0.98
PICKS = [
    ("Part3", "chest_part3.png", 0.97),   # 与 II级部件箱（非目标）干扰 0.960，必须 >0.96
    ("TrainBegin", "chest_train_begin.png", 0.85),
    ("TrainHigh", "chest_train_high.png", 0.88),
    ("TrainExBegin", "chest_train_ex_begin.png", 0.90),
    ("TrainExMid", "chest_train_ex_mid.png", 0.90),
    ("TrainExHigh", "chest_train_ex_high.png", 0.90),
    ("TrainExTop", "chest_train_ex_top.png", 0.90),
    ("CommonBox", "chest_common_box.png", 0.90),
    ("SmuggleBox", "chest_smuggle_box.png", 0.90),
    ("GearHigh", "chest_gear_high.png", 0.88),
    ("GunHigh", "chest_gun_high.png", 0.90),
    ("TorpedoHigh", "chest_torpedo_high.png", 0.90),
    ("PlaneHigh", "chest_plane_high.png", 0.90),
    ("AaHigh", "chest_aa_high.png", 0.90),
    ("DeviceHigh", "chest_device_high.png", 0.90),
]

PICK_ROI = [180, 90, 1090, 630]   # 必须覆盖 row4（图标中心 y=665，下沿到 ~713）
PICK_TIMEOUT = 1200               # 候选节点失败一次烧 timeout*loop，默认 20000 会爆预算
PICK_MAX_HIT = 12                 # 同类型最多开 12 次：装备库容满时一次 MAX 只吃一部分，要能反复补开

pipeline = {}
pipeline["ChestStart"] = {
    "recognition": "DirectHit",
    "action": "DoNothing",
    "timeout": 600000,
    "anchor": {"Resume": "ChestResume"},
    "next": ["ChestOnMain", "NaviCommon"],
}
pipeline["ChestResume"] = {
    "recognition": "DirectHit",
    "action": "DoNothing",
    "next": ["ChestOnMain"],
}
pipeline["ChestOnMain"] = {
    "recognition": "TemplateMatch",
    "template": "common/ui_main.png",
    "roi": [10, 650, 90, 60],
    "threshold": 0.7,
    "action": "DoNothing",
    "timeout": 2500,
    "next": ["NaviDrawerClose", "ChestClickDepot"],
    "on_error": ["NaviCommon"],
}
pipeline["ChestClickDepot"] = {
    "recognition": "TemplateMatch",
    "template": "common/nav_depot.png",
    "roi": [333, 651, 149, 51],
    "threshold": 0.7,
    "action": "Click",
    "post_delay": 3500,
    "max_hit": 1,
    "next": ["ChestClickTab"],
}
pipeline["ChestClickTab"] = {
    "recognition": "DirectHit",
    "action": "Click",
    "target": [100, 300],
    "post_delay": 2000,
    "next": ["ChestOnTab"],
}
pipeline["ChestOnTab"] = {
    "recognition": "OCR",
    "expected": [".*宝箱.*"],
    "roi": [45, 260, 130, 80],
    "threshold": 0.7,
    "action": "DoNothing",
    "timeout": 3000,
    "next": ["ChestRoot"],
    "on_error": ["ChestClickTabRetry"],
}
pipeline["ChestClickTabRetry"] = {
    "recognition": "DirectHit",
    "action": "Click",
    "target": [100, 300],
    "post_delay": 2500,
    "next": ["ChestOnTabRetry"],
}
pipeline["ChestOnTabRetry"] = {
    "recognition": "OCR",
    "expected": [".*宝箱.*"],
    "roi": [45, 260, 130, 80],
    "threshold": 0.7,
    "action": "DoNothing",
    "timeout": 3000,
    "next": ["ChestRoot"],
    "on_error": ["ChestExit"],
}

# 根：每轮只认一个状态，动作完回到根
pipeline["ChestRoot"] = {
    "recognition": "DirectHit",
    "action": "DoNothing",
    "timeout": 6000,
    "rate_limit": 300,
    "max_hit": 300,
    "next": ["ChestReward", "ChestInfo"] + ["ChestPick_" + p[0] for p in PICKS],
    "on_error": ["ChestScroll", "ChestExit"],
}
pipeline["ChestReward"] = {
    "recognition": "OCR",
    "expected": [".*点击继续.*"],
    "roi": [500, 570, 240, 60],
    "threshold": 0.7,
    "action": "Click",
    "post_delay": 1200,
    "timeout": 2500,
    "rate_limit": 300,
    "max_hit": 80,
    "next": ["ChestRoot"],
}
pipeline["ChestInfo"] = {
    "recognition": "OCR",
    "expected": [".*使用数量.*"],
    "roi": [340, 360, 400, 60],
    "threshold": 0.7,
    "action": "DoNothing",
    "timeout": 1200,
    "rate_limit": 300,
    "max_hit": 80,
    "next": ["ChestSelfSelect", "ChestMax"],
}
# 「请自选内容」型训练合集：必须先在内容条里勾一项，否则「打开」是灰的（点不动）
pipeline["ChestSelfSelect"] = {
    "recognition": "OCR",
    "expected": [".*请自选内容.*"],
    "roi": [340, 210, 480, 45],
    "threshold": 0.7,
    "action": "Click",
    "target": [355, 285],          # 第一个内容条（勾选后才可开）
    "post_delay": 900,
    "timeout": 1500,
    "next": ["ChestMax"],
}
pipeline["ChestMax"] = {
    "recognition": "DirectHit",
    "action": "Click",
    "target": [927, 396],
    "post_delay": 600,
    "next": ["ChestOpen"],
}
# 「打开」是 DirectHit，永远"成功"，失败只能靠 next 候选兜底：
# 奖励浮层出现 → ChestReward；面板还留着 → ChestOpenFail；弹了已满/不足提示 → ChestFull
pipeline["ChestOpen"] = {
    "recognition": "DirectHit",
    "action": "Click",
    "target": [904, 649],
    "post_delay": 2000,
    "timeout": 5000,
    "next": ["ChestReward", "ChestConfirm", "ChestOpenFail", "ChestFull"],
    "on_error": ["ChestRoot"],
}
# 自选型开箱会弹「确定要选择「X」×N 吗？」确认框
pipeline["ChestConfirm"] = {
    "recognition": "OCR",
    "expected": [".*确定要选择.*"],
    "roi": [400, 300, 600, 80],
    "threshold": 0.7,
    "action": "Click",
    "target": [838, 461],
    "post_delay": 2500,
    "timeout": 2500,
    "next": ["ChestReward"],
}
pipeline["ChestOpenFail"] = {
    "recognition": "OCR",
    "expected": [".*使用数量.*"],
    "roi": [340, 360, 400, 60],
    "threshold": 0.7,
    "action": "Click",
    "target": [993, 23],
    "post_delay": 1200,
    "timeout": 2000,
    "next": ["ChestExit"],
}
pipeline["ChestFull"] = {
    "recognition": "OCR",
    "expected": [".*(已满|容量不足|仓库已满).*"],
    "roi": [380, 280, 520, 180],
    "threshold": 0.7,
    "action": "Click",
    "target": [840, 462],
    "post_delay": 1200,
    "timeout": 2000,
    "next": ["ChestExit"],
}
pipeline["ChestScroll"] = {
    "recognition": "DirectHit",
    "action": "Swipe",
    "begin": [900, 560],
    "end": [900, 220],
    "duration": 400,
    "post_delay": 1500,
    "timeout": 4000,
    "max_hit": 4,
    "next": ["ChestRoot"],
    "on_error": ["ChestExit"],
}
pipeline["ChestExit"] = {
    "recognition": "TemplateMatch",
    "template": "common/ui_subpage_home.png",
    "roi": [185, 10, 110, 60],
    "threshold": 0.7,
    "action": "Click",
    "post_delay": 2500,
    "timeout": 3000,
    "max_hit": 6,
    "next": ["ChestExit"],
    "on_error": ["ChestDone"],
}
pipeline["ChestDone"] = {
    "recognition": "TemplateMatch",
    "template": "common/ui_main.png",
    "roi": [10, 650, 90, 60],
    "threshold": 0.7,
    "action": "DoNothing",
    "timeout": 3000,
    "focus": {"success": "仓库开箱完成，已返回主界面"},
}

for suffix, tpl, th in PICKS:
    pipeline["ChestPick_" + suffix] = {
        "recognition": "TemplateMatch",
        "template": "warehouse/" + tpl,
        "roi": PICK_ROI,
        "threshold": th,
        "action": "Click",
        "post_delay": 1500,
        "timeout": PICK_TIMEOUT,
        "max_hit": PICK_MAX_HIT,
        "next": ["ChestRoot"],
    }

OUT.write_text(json.dumps(pipeline, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
print("wrote", OUT, "nodes=", len(pipeline))
