# -*- coding: utf-8 -*-
"""失败台账：把 `on_error` 截图按性质分成三类，只把"真失败"当失败。

数据源：`<debug>/on_error/*.png` —— Maa 在 `on_error` 触发时自动截图，
文件名形如 `2026.11.14-22.10.37.275_节点名.png`。

关键：**`on_error` 截图 ≠ 失败**。Maa 在三种情况下走 on_error，性质完全不同：

  1. 【正常分支】inverse 节点：`inverse=true` 时，"识别到"被反转为"识别失败"，
     于是"识别到 → 走 on_error"。这是设计好的正常路径。
     例：`ShopWaitClosed` 用 inverse 找"取消"按钮，找到弹窗就走 on_error 去点掉。
  2. 【兜底路径】DirectHit 路由节点：DirectHit 恒成功，它自身的 on_error 永远不会
     因"识别失败"触发；它的 on_error 表示"next 列表所有候选都落空"。
     这可能是正常（任务派完 / 商品买完 / 没货），也可能是界面卡住，需人工判断。
  3. 【真失败】识别节点（TemplateMatch / OCR / FeatureMatch / ColorMatch / And / Or）
     识别失败触发 on_error。**这才是真正要重点看的。**

所以默认只把第 3 类列为"失败"；第 1、2 类单独列出，不混进失败数，
避免被"132 次失败"这种数字误导（其中大部分是正常控制流）。

用法：
    python tools/failure_ledger.py              # 汇总（三类分开）
    python tools/failure_ledger.py --real-only  # 只看真失败
    python tools/failure_ledger.py --entry Exp  # 只看前缀匹配的功能
    python tools/failure_ledger.py --md         # 输出 markdown
    python tools/failure_ledger.py --screens    # 同时列出失败截图路径
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from check_assets import load_jsonc
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_assets import load_jsonc

PROJECT = Path(__file__).resolve().parent.parent
PIPE_DIR = PROJECT / "assets" / "resource" / "pipeline"

TS_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2})\.(\d{3})_(.+)$")

# 节点名 → 其 pipeline 节点定义缓存
_NODE_CACHE: dict[str, dict] | None = None

# 真正的识别类 recognition（识别失败 = 真失败）
REAL_RECO = ("TemplateMatch", "OCR", "FeatureMatch", "ColorMatch", "And", "Or", "NeuralNetworkClassify")

# 入口名 → 功能中文名（从 interface.json 解析更准，但这里是离线兜底）
FALLBACK_LABELS = {
    "TaskClaim": "领取任务奖励",
    "Expedition": "远征领取与派遣",
    "Exp": "远征领取与派遣",
    "GiftClaim": "领取免费礼包",
    "SecretaryTalk": "与秘书舰互动",
    "Exercise": "参与演习",
    "Naval": "收取港区资源并换班",
    "DailySweep": "自动扫荡日常关卡",
    "Craft": "自动合成仓库道具",
    "Shop": "自动兑换补给商店",
    "Mail": "领取临期邮件",
    "Beach": "沙滩训练舰灵等级",
    "Main": "主线关卡托管",
    "Navi": "公共归位（全部功能共用）",
    "T5": "旧版临时节点",
    "P1": "旧版临时节点",
}


def load_all_nodes() -> dict[str, dict]:
    """把 13 个 pipeline 的所有节点定义读进一个 dict（全局节点空间）。"""
    global _NODE_CACHE
    if _NODE_CACHE is not None:
        return _NODE_CACHE
    nodes: dict[str, dict] = {}
    if not PIPE_DIR.is_dir():
        _NODE_CACHE = nodes
        return nodes
    for f in sorted(PIPE_DIR.glob("*.json")):
        try:
            data = load_jsonc(f)
        except Exception:
            continue
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict):
                    nodes[k] = v
    _NODE_CACHE = nodes
    return nodes


def classify(node: str) -> str:
    """把节点按失败性质分类：'real' | 'inverse' | 'route' | 'unknown'。"""
    nodes = load_all_nodes()
    v = nodes.get(node)
    if v is None:
        return "unknown"
    if v.get("inverse"):
        return "inverse"          # 识别到 → on_error，正常分支
    rec = v.get("recognition")
    if rec == "DirectHit":
        return "route"            # 恒成功，on_error 表示 next 全落空，兜底
    if rec in REAL_RECO or (isinstance(rec, str) and rec not in ("DirectHit",)):
        return "real"             # 真识别失败
    return "real"


def find_debug_roots() -> list[Path]:
    roots: list[Path] = []
    d = PROJECT / "debug"
    if d.is_dir():
        roots.append(d)
    rel = Path("E:/DSH/MaaFX/release/win-x64/debug")
    if rel.is_dir():
        roots.append(rel)
    for extra in (Path.home() / "WorkBuddy",):
        if extra.is_dir():
            for sub in extra.glob("*/debug_*"):
                if (sub / "on_error").is_dir() or (sub / "maafw.log").is_file():
                    roots.append(sub)
    return roots


def collect_failures(roots: list[Path]):
    """返回 [(时间戳, 节点名, 截图路径, 来源目录)] 与 {节点名: 出现次数}"""
    events: list[tuple[str, str, Path, str]] = []
    for root in roots:
        oe = root / "on_error"
        if not oe.is_dir():
            continue
        for p in oe.glob("*"):
            if p.suffix.lower() not in (".png", ".jpg"):
                continue
            m = TS_RE.match(p.stem)
            if not m:
                continue
            ts = f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}"
            node = m.group(8)
            events.append((ts, node, p, root.name))
    events.sort(key=lambda e: e[0])
    return events


def parse_log_failures(roots: list[Path]) -> Counter:
    """保留接口但不再默认使用（见文件头说明，Recognition.Failed 会虚高）。"""
    cnt: Counter[str] = Counter()
    pat = re.compile(r'msg=Node\.Recognition\.Failed.*?"name":"([A-Za-z0-9_]+)"')
    for root in roots:
        log = root / "maafw.log"
        if not log.is_file():
            continue
        try:
            for ln in log.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = pat.search(ln)
                if m:
                    cnt[m.group(1)] += 1
        except Exception:
            continue
    return cnt


def group_by_feature(nodes: list[str]) -> dict[str, list[str]]:
    """按入口前缀把节点归到功能，长的前缀优先（DailySweep 先于 Daily）。"""
    prefixes = sorted(FALLBACK_LABELS, key=len, reverse=True)
    groups: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        hit = next((p for p in prefixes if n.startswith(p)), None)
        groups[hit or "（未归类）"].append(n)
    return groups


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", help="只看节点名以此开头的记录")
    ap.add_argument("--md", action="store_true", help="输出 markdown")
    ap.add_argument("--screens", action="store_true", help="列出失败截图路径")
    ap.add_argument("--limit", type=int, default=0, help="每功能最多显示几个节点")
    ap.add_argument("--real-only", action="store_true", help="只看真失败（识别节点识别失败）")
    args = ap.parse_args()

    roots = find_debug_roots()
    events = collect_failures(roots)

    if args.entry:
        events = [e for e in events if e[1].startswith(args.entry)]

    if not events:
        print("没有找到任何 on_error 截图。")
        print(f"已扫描目录：{len(roots)} 个")
        for r in roots[:10]:
            print(f"  - {r}")
        return 0

    # 按性质分组
    buckets: dict[str, Counter[str]] = {
        "real": Counter(),
        "inverse": Counter(),
        "route": Counter(),
        "unknown": Counter(),
    }
    for ts, node, p, src in events:
        buckets[classify(node)][node] += 1

    kind_label = {
        "real": "真失败（识别节点识别失败，重点看）",
        "inverse": "正常分支（inverse 节点，识别到→on_error，不算失败）",
        "route": "兜底路径（DirectHit 路由节点，next 全落空，需人工判断）",
        "unknown": "节点已不在 pipeline（历史遗留）",
    }

    def render(bucket_key: str, title: str) -> None:
        cnt = buckets[bucket_key]
        if not cnt:
            return
        total = sum(cnt.values())
        print(f"\n【{title}】共 {total} 次")
        groups = group_by_feature(list(cnt))
        for prefix, nodes in sorted(groups.items(), key=lambda kv: -sum(cnt[n] for n in kv[1])):
            label = FALLBACK_LABELS.get(prefix, prefix)
            ftotal = sum(cnt[n] for n in nodes)
            print(f"  ▸ {label}（{ftotal} 次）")
            shown = nodes if args.limit <= 0 else nodes[: args.limit]
            for n in sorted(shown, key=lambda x: -cnt[x]):
                print(f"      {cnt[n]:3}× {n}")
            if args.limit > 0 and len(nodes) > args.limit:
                print(f"      ... 另有 {len(nodes) - args.limit} 个节点")

    print(f"扫描 {len(roots)} 个 debug 目录，{len(events)} 张 on_error 截图")

    if args.real_only:
        render("real", kind_label["real"])
    else:
        for key in ("real", "inverse", "route", "unknown"):
            render(key, kind_label[key])

    if args.screens:
        print("\n失败截图（最近 20 张）：")
        for ts, node, p, src in events[-20:]:
            print(f"    {ts}  {node:32}  [{classify(node)}]  {p}")
        print()

    real_total = sum(buckets["real"].values())
    print(f"\n提示：真正的失败是「真失败」那组（{real_total} 次），其余是正常控制流。")
    print("      写新功能前对照真失败组逐条自查，别被总数带偏。")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
