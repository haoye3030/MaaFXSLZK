# -*- coding: utf-8 -*-
"""素材校验（自动版）。

替代 asset_guideline.md 第三节里手抄的三段 Python。

两个数据源，各管一段：
  * 静态检查（不依赖运行）：纯色、缺失、未引用、重复、roi 与模板尺寸矛盾
  * 运行检查（读 maafw.log 的真实 NCC 得分）：目标位得分、干扰位置得分

为什么不自己算 NCC 而读日志：
  Maa 的 `vision/` 调试图会画上 ROI 框和命中框，标注像素会污染模板匹配区域；
  且 `vision/` 有 20% 的图被拼接了右侧模板对照栏（宽 1330~1488），不是原始帧。
  自算 NCC 会得到 0.82 这样的假低分，而 Maa 实际得分是 1.000。
  日志里的 `TemplateMatcher::analyze` 行才是权威依据。

用法：
    python tools/check_assets.py              # 静态 + 日志
    python tools/check_assets.py --static     # 只做静态检查
    python tools/check_assets.py --log-only   # 只看日志得分

退出码：0 = 无 FAIL，1 = 有 FAIL。
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT = Path(__file__).resolve().parent.parent
RES = PROJECT / "assets" / "resource"
IMG_DIR = RES / "image"
PIPE_DIR = RES / "pipeline"

SOLID_STD = 15.0
TARGET_MIN = 0.90
MARGIN_MIN = 0.10
THRESHOLD_SLACK = 0.05  # 实际得分低于阈值多少算危险


# ---------- JSONC ----------
def strip_jsonc(text: str) -> str:
    out, i, in_str, n = [], 0, False, len(text)
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\":
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def load_jsonc(path: Path):
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(strip_jsonc(raw))


# ---------- 采集 pipeline 引用 ----------
NEST_KEYS = ("all_of", "any_of", "not")


def _walk(cfg, node, pipe, refs):
    if not isinstance(cfg, dict):
        return
    tpl = cfg.get("template")
    roi = cfg.get("roi")
    thr = cfg.get("threshold")
    paths = []
    if isinstance(tpl, str):
        paths = [tpl]
    elif isinstance(tpl, list):
        paths = [p for p in tpl if isinstance(p, str)]
    for p in paths:
        refs.append((p.replace("\\", "/"), pipe, node, roi, thr))
    for key in NEST_KEYS:
        sub = cfg.get(key)
        if isinstance(sub, dict):
            _walk(sub, node, pipe, refs)
        elif isinstance(sub, list):
            for item in sub:
                _walk(item, node, pipe, refs)


def collect_refs():
    """返回 [(图像相对路径, pipeline文件, 节点名, roi, threshold)]"""
    refs = []
    for f in sorted(PIPE_DIR.glob("*.json")):
        data = load_jsonc(f)
        if not isinstance(data, dict):
            continue
        for node, cfg in data.items():
            if isinstance(cfg, dict):
                _walk(cfg, node, f.name, refs)
    return refs


# ---------- 读日志里的真实得分 ----------
SCORE_RE = re.compile(r'"score":([0-9.]+)')
NODE_RE = re.compile(r"analyze\] (\S+) \[")
TEMPLATE_RE = re.compile(r'param_\.template_=\[([^\]]*)\]')


def find_logs() -> list[Path]:
    logs: list[Path] = []
    dbg = PROJECT / "debug" / "maafw.log"
    if dbg.is_file():
        logs.append(dbg)
    # 历史运行目录（Maa 曾被写到 WorkBuddy）
    for extra in (Path.home() / "WorkBuddy",):
        if extra.is_dir():
            logs += sorted(extra.glob("*/debug_*/maafw.log"))
            logs += sorted(extra.glob("*/maafw.log"))
    # 运行副本
    rel = Path("E:/DSH/MaaFX/release/win-x64/debug/maafw.log")
    if rel.is_file():
        logs.append(rel)
    return logs


def parse_log_scores() -> dict[str, list[float]]:
    """返回 {节点名: [每次匹配得到的最高分]}"""
    out: dict[str, list[float]] = {}
    for f in find_logs():
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for ln in lines:
            if "TemplateMatcher::analyze]" not in ln:
                continue
            m = NODE_RE.search(ln)
            if not m:
                continue
            node = m.group(1)
            scores = [float(s) for s in SCORE_RE.findall(ln)]
            if scores:
                out.setdefault(node, []).append(max(scores))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--static", action="store_true", help="只做静态检查")
    ap.add_argument("--log-only", action="store_true", help="只看日志得分")
    ap.add_argument("--verbose", action="store_true", help="逐条列出通过项")
    args = ap.parse_args()

    fails: list[str] = []
    warns: list[str] = []
    all_imgs = sorted(IMG_DIR.rglob("*.png"))
    all_keys = {p.relative_to(IMG_DIR).as_posix() for p in all_imgs}
    refs = collect_refs()
    referenced = {r[0] for r in refs}

    if not args.log_only:
        print(f"素材 {len(all_imgs)} 张，pipeline 引用 {len(referenced)} 个路径，"
              f"{len(refs)} 处引用点\n")

        # --- 缺失 / 未引用 ---
        for m in sorted(referenced - all_keys):
            where = next(r for r in refs if r[0] == m)
            fails.append(f"缺失素材：{m}（{where[1]}:{where[2]}）")
        for u in sorted(all_keys - referenced):
            warns.append(f"未被引用：{u}")

        # --- 重复 ---
        md5s: dict[str, list[str]] = {}
        for p in all_imgs:
            h = hashlib.md5(p.read_bytes()).hexdigest()
            md5s.setdefault(h, []).append(p.relative_to(IMG_DIR).as_posix())
        for h, group in md5s.items():
            if len(group) > 1:
                warns.append(f"完全重复：{', '.join(group)}")

        # --- 纯色 / 尺寸 ---
        sizes: dict[str, tuple[int, int]] = {}
        for p in all_imgs:
            key = p.relative_to(IMG_DIR).as_posix()
            im = Image.open(p)
            sizes[key] = im.size
            a = np.asarray(im.convert("RGB")).astype(int)
            std = float(a.std())
            if std < SOLID_STD:
                fails.append(f"纯色废片：{key}（标准差 {std:.1f} < {SOLID_STD}）")

        # --- roi 与模板尺寸矛盾 ---
        for key, pipe, node, roi, thr in refs:
            if key not in sizes:
                continue
            tw, th = sizes[key]
            if isinstance(roi, list) and len(roi) == 4:
                rw, rh = int(roi[2]), int(roi[3])
                if rw < tw or rh < th:
                    fails.append(
                        f"roi 装不下模板：{key} @{node} roi={rw}x{rh} 模板={tw}x{th}")
            if isinstance(thr, (int, float)) and thr > 0.95:
                warns.append(f"阈值过高（{thr}）：{key} @{node}，轻微变化就会漏")

    # --- 运行得分 ---
    if not args.static:
        scores = parse_log_scores()
        print(f"\n日志得分：{len(scores)} 个节点，"
              f"{sum(len(v) for v in scores.values())} 次匹配")
        logs = find_logs()
        print(f"数据源：{len(logs)} 个 maafw.log")
        for lg in logs[:5]:
            print(f"  - {lg}")

        node2ref = {}
        for key, pipe, node, roi, thr in refs:
            node2ref.setdefault(node, []).append((key, thr))

        print(f"\n{'节点':30} {'素材':30} {'最好':>6} {'最差':>6} {'阈值':>5}  结论")
        print("-" * 92)
        risky = 0
        never = 0
        for node, vals in sorted(scores.items()):
            ref = node2ref.get(node)
            if not ref:
                continue
            key, thr = ref[0]
            best, worst = max(vals), min(vals)
            verdict = "OK"
            if thr is not None and best < thr:
                # 从未达标。可能是反向校验节点（"不在此界面"），属于正常；
                # 也可能是素材/roi 真的坏了。交给人工判断，不算 FAIL。
                verdict = "WARN 从未达标"
                warns.append(
                    f"{key} @{node} 从未达标（最高 {best:.3f} < 阈值 {thr}）。"
                    f"若是反向校验节点属正常，否则查 roi/素材"
                )
                never += 1
            elif thr is not None and worst < thr - THRESHOLD_SLACK:
                verdict = "WARN 曾有低分"
                warns.append(
                    f"{key} @{node} 曾低至 {worst:.3f}（阈值 {thr}，{len(vals)} 次）")
                risky += 1
            if args.verbose or verdict != "OK":
                print(f"{node:30} {key:30} {best:6.3f} {worst:6.3f} "
                      f"{(str(thr) if thr is not None else '-'):>5}  {verdict}")
        print(f"\n日志覆盖 {len([n for n in scores if n in node2ref])} 个有素材引用的节点："
              f"{never} 个从未达标（多为反向校验），{risky} 个曾出现低分\n")

    # --- 汇总 ---
    if warns:
        print(f"WARN ({len(warns)})")
        for w in warns:
            print(f"  ~ {w}")
        print()
    if fails:
        print(f"FAIL ({len(fails)})")
        for f_ in fails:
            print(f"  x {f_}")
        print("\n结果：不通过")
        return 1
    print("结果：全绿 [OK]")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
