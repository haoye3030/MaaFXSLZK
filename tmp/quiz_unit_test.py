# -*- coding: utf-8 -*-
"""离线单测：QuizAnswer / QuizGirl 识别器（不碰模拟器，喂已存截图）。

用法: python tmp/quiz_unit_test.py
依赖: 系统 python 3.12 + maafw 5.15 + Pillow（进程内注册路径）
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT = Path(r"E:\DSH\MaaFX\MaaFXSLZK")
SHOTS = Path(r"E:\DSH\MaaFX\tmp\quiz_out")
sys.path.insert(0, str(PROJECT / "agent"))

import maa
from maa.controller import AdbController
from maa.pipeline import JCustomRecognition, JRecognitionType, JTemplateMatch
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit

from quiz import QuizAnswer, QuizGirl

FAILS = []


def load(name):
    arr = np.array(Image.open(SHOTS / name).convert("RGB"))
    return np.ascontiguousarray(arr[:, :, ::-1])  # RGB -> BGR（识别链路要求 BGR）


def post(tasker, reco_type, param, image):
    job = tasker.post_recognition(reco_type, param, image)
    detail = job.wait().get()
    ids = list(getattr(detail, "node_id_list", None) or [])
    if not ids:
        return None
    return tasker.get_node_detail(ids[0]).recognition


def expect(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def main():
    Toolkit.init_option(str(Path(maa.__file__).parent / "bin"))
    # DbgController 需要 MaaDbgControlUnit 原生库，本机 5.15 pip 包未带；
    # 用真实 AdbController 只做 Tasker 绑定，识别喂的是本地截图（不发点击/截图）
    ctrl = AdbController(
        adb_path=r"C:/Program Files/Netease/MuMu/nx_main/adb.exe",
        address="127.0.0.1:16384",
        config={"input": "adb_shell", "screencap": "encap_png_by_netcat"},
    )
    ok = ctrl.post_connection().wait().succeeded
    print("AdbController connect:", ok)
    print("JRecognitionType members:", [m.name for m in JRecognitionType])

    res = Resource()
    print("post_bundle:", res.post_bundle(PROJECT / "assets" / "resource").wait().succeeded)
    res.register_custom_recognition("QuizAnswer", QuizAnswer())
    res.register_custom_recognition("QuizGirl", QuizGirl())

    tasker = Tasker()
    tasker.bind(res, ctrl)

    # ---------- 1) 模板匹配路径解析（quiz/quiz_mark.png 能否从资源包加载） ----------
    print("\n[1] TemplateMatch quiz/quiz_mark.png on 20_after_refresh.png")
    shot_room = load("20_after_refresh.png")
    rd = post(
        tasker,
        JRecognitionType.TemplateMatch,
        JTemplateMatch(template=["quiz/quiz_mark.png"], roi=(20, 100, 1240, 520), threshold=[0.8]),
        shot_room,
    )
    print("   hit:", getattr(rd, "hit", None), "box:", getattr(rd, "box", None), "detail:", getattr(rd, "detail", None))
    if rd is not None and getattr(rd, "hit", False):
        br = getattr(rd, "best_result", None)
        print("   best score:", getattr(br, "score", None))
        expect(getattr(br, "score", 0) > 0.9, "quiz_mark 模板在满员房间里 NCC>0.9")
    else:
        expect(False, "quiz_mark 模板应命中满员房间的 ? 徽章")

    # ---------- 2) QuizAnswer 题目界面 ----------
    print("\n[2] QuizAnswer on 42_tap_640_600.png")
    q_img = load("42_tap_640_600.png")
    rd = post(
        tasker,
        JRecognitionType.Custom,
        JCustomRecognition(custom_recognition="QuizAnswer", custom_recognition_param="{}"),
        q_img,
    )
    print("   hit:", getattr(rd, "hit", None), "box:", getattr(rd, "box", None))
    print("   detail:", getattr(rd, "detail", None))
    expect(rd is not None and getattr(rd, "hit", False), "题目界面应命中")
    if rd is not None and getattr(rd, "hit", False):
        box = rd.box
        expect(abs(box[1] - 281) < 40, f"命中选项应为 460 那条（y≈281），实际 {box}")

    # ---------- 3) QuizAnswer 非题目界面 ----------
    print("\n[3] QuizAnswer on 41_after_confirm2.png (VN 立绘，无选项)")
    rd = post(
        tasker,
        JRecognitionType.Custom,
        JCustomRecognition(custom_recognition="QuizAnswer", custom_recognition_param="{}"),
        load("41_after_confirm2.png"),
    )
    print("   hit:", getattr(rd, "hit", None), "detail:", getattr(rd, "detail", None))
    expect(rd is not None and not getattr(rd, "hit", True), "非题目界面不应命中")

    # ---------- 4) QuizGirl 满员房间：连续取点应各不相同 ----------
    print("\n[4] QuizGirl on 20_after_refresh.png（连续取点）")
    clicks = []
    for i in range(8):
        rd = post(
            tasker,
            JRecognitionType.Custom,
            JCustomRecognition(custom_recognition="QuizGirl", custom_recognition_param="{}"),
            shot_room,
        )
        hit = rd is not None and getattr(rd, "hit", False)
        detail = getattr(rd, "detail", None)
        print(f"   #{i} hit={hit} box={getattr(rd, 'box', None)} detail={detail}")
        if not hit:
            break
        clicks.append((rd.box[0] + rd.box[2] // 2, rd.box[1] + rd.box[3] // 2))
    print("   clicks:", clicks)
    expect(len(clicks) >= 4, f"满员房间应至少给出 4 个不同点击点（实际 {len(clicks)}）")
    expect(len(set(clicks)) == len(clicks), "各次取点不应重复")
    # 与实测舰灵头部坐标对照（误差容忍 60px）
    heads = [(317, 400), (540, 345), (420, 496), (723, 245), (840, 300), (680, 390)]
    for cx, cy in clicks:
        near = min(abs(cx - hx) + abs(cy - hy) for hx, hy in heads)
        print(f"   click ({cx},{cy}) 最近头部曼哈顿距离 {near}")
        expect(near <= 90, f"点击点 ({cx},{cy}) 应落在某个舰灵头部附近")

    # ---------- 5) QuizGirl 空房间 ----------
    print("\n[5] QuizGirl on 71_consult_again.png（空房间）")
    rd = post(
        tasker,
        JRecognitionType.Custom,
        JCustomRecognition(custom_recognition="QuizGirl", custom_recognition_param="{}"),
        load("71_consult_again.png"),
    )
    print("   hit:", getattr(rd, "hit", None), "detail:", getattr(rd, "detail", None))
    expect(rd is not None and not getattr(rd, "hit", True), "空房间不应命中")

    # ---------- 6) 索引任务界面（21_port.png 港区地图）不应命中 QuizGirl ----------
    print("\n[6] QuizGirl on 21_port.png（港区地图）")
    rd = post(
        tasker,
        JRecognitionType.Custom,
        JCustomRecognition(custom_recognition="QuizGirl", custom_recognition_param="{}"),
        load("21_port.png"),
    )
    print("   hit:", getattr(rd, "hit", None), "detail:", getattr(rd, "detail", None))
    expect(rd is not None and not getattr(rd, "hit", True), "港区地图不应命中 QuizGirl")

    print("\n" + "=" * 60)
    if FAILS:
        print(f"{len(FAILS)} 项失败：")
        for f in FAILS:
            print("  -", f)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
