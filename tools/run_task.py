# -*- coding: utf-8 -*-
"""任务运行器：一条命令跑任务，替代散落的临时脚本。

背景：
  此前每次诊断都由 AI 现写一个临时 .py 到 %TEMP%，重新实现
  "连设备 → 载资源 → 开 Tasker → 跑任务 → 收调试图" 这一整套样板。
  实测 11-17 一天产生了 152 个这样的临时脚本。
  这个文件把样板收成一处，以后只传参数。

用法：
    python tools/run_task.py --list               # 列出所有任务入口
    python tools/run_task.py BeachStart           # 跑单个任务
    python tools/run_task.py BeachStart MainStart # 顺序跑多个
    python tools/run_task.py --all                # 跑全部（按 interface.json 顺序）
    python tools/run_task.py BeachStart --no-draw # 不存调试图（更快）
    python tools/run_task.py --device emulator-5554
    python tools/run_task.py BeachStart --timeout 600

退出码：0 = 全部成功，1 = 有任务失败，2 = 环境问题（设备/资源）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
RES = PROJECT / "assets" / "resource"
INTERFACE = PROJECT / "assets" / "interface.json"
DEBUG = PROJECT / "debug"

ADB_DEFAULT = r"C:/Program Files/Netease/MuMu/nx_main/adb.exe"
DEVICE_DEFAULT = "127.0.0.1:16384"


# ---------- interface.json 是 JSONC ----------
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


def load_interface():
    raw = INTERFACE.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(strip_jsonc(raw))


def list_tasks():
    data = load_interface()
    return [(t.get("label") or t["name"], t["entry"]) for t in data.get("task", [])]


def main() -> int:
    ap = argparse.ArgumentParser(description="MaaFramework 任务运行器")
    ap.add_argument("entries", nargs="*", help="任务入口名，如 BeachStart")
    ap.add_argument("--list", action="store_true", help="列出所有任务入口")
    ap.add_argument("--all", action="store_true", help="跑全部任务")
    ap.add_argument("--device", default=DEVICE_DEFAULT, help=f"ADB 地址（默认 {DEVICE_DEFAULT}）")
    ap.add_argument("--adb", default=ADB_DEFAULT, help="adb.exe 路径")
    ap.add_argument("--timeout", type=int, default=900, help="单任务超时秒数（默认 900）")
    ap.add_argument("--no-draw", action="store_true", help="不保存调试图")
    ap.add_argument("--save-on-error", action="store_true", default=True,
                    help="失败时截图（默认开）")
    ap.add_argument("--out", default=None, help="调试输出目录（默认 debug/run_<时间戳>）")
    args = ap.parse_args()

    if args.list:
        tasks = list_tasks()
        print(f"{'入口':24} 说明")
        print("-" * 70)
        for label, entry in tasks:
            print(f"{entry:24} {label}")
        return 0

    entries = list(args.entries)
    if args.all:
        entries = [e for _, e in list_tasks()]
    if not entries:
        ap.print_help()
        return 2

    # 环境检查
    if not Path(args.adb).is_file():
        print(f"[!] 找不到 adb：{args.adb}")
        print("    用 --adb 指定，或确认 MuMu 安装路径。")
        return 2
    if not RES.is_dir():
        print(f"[!] 找不到资源目录：{RES}")
        return 2

    try:
        import maa
        from maa.controller import AdbController
        from maa.library import Library
        from maa.resource import Resource
        from maa.tasker import Tasker
        from maa.toolkit import Toolkit
    except ImportError as e:
        print(f"[!] 无法导入 MaaFramework Python 绑定：{e}")
        print("    pip install MaaFw")
        return 2

    out_dir = Path(args.out) if args.out else (
        DEBUG / f"run_{time.strftime('%m%d-%H%M%S')}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"MaaFw {Library.version()}")
    print(f"adb   {args.adb}")
    print(f"设备  {args.device}")
    print(f"输出  {out_dir}")
    print(f"任务  {len(entries)} 个\n")

    Toolkit.init_option(str(Path(maa.__file__).parent / "bin"))
    ctrl = AdbController(
        adb_path=args.adb,
        address=args.device,
        config={"input": "adb_shell", "screencap": "encap_png_by_netcat"},
    )
    if not ctrl.post_connection().wait().succeeded:
        print("[!] 设备连接失败。确认模拟器已启动、ADB 调试已开。")
        return 2

    res = Resource()
    if not res.post_bundle(RES).wait().succeeded:
        print("[!] 资源加载失败。先跑 `npx @nekosu/maa-tools check` 看是不是 JSON 重复键。")
        return 2

    # 注册 agent/recognizers.py 的自定义识别器（进程内路径，供含 Custom 节点的 pipeline 测试；
    # MFAAvalonia 生产环境走 agent 子进程，不经此路径）
    try:
        sys.path.insert(0, str(PROJECT / "agent"))
        from quiz import QuizAnswer, QuizGirl  # noqa: E402
        from recognizers import ExpIsNightWindow, ExpTimeCheck  # noqa: E402
        res.register_custom_recognition("ExpTimeCheck", ExpTimeCheck())
        res.register_custom_recognition("ExpIsNightWindow", ExpIsNightWindow())
        res.register_custom_recognition("QuizAnswer", QuizAnswer())
        res.register_custom_recognition("QuizGirl", QuizGirl())
    except Exception as e:
        print(f"[!] 自定义识别器注册失败（Custom 节点将不可用）：{e}")

    Tasker.set_log_dir(str(out_dir))
    Tasker.set_save_draw(not args.no_draw)
    Tasker.set_save_on_error(args.save_on_error)

    tasker = Tasker()
    tasker.bind(res, ctrl)

    results = []
    for i, entry in enumerate(entries, 1):
        print(f"[{i}/{len(entries)}] {entry} ... ", end="", flush=True)
        t0 = time.time()
        try:
            r = tasker.post_task(entry).wait()
            ok = bool(r.succeeded)
        except Exception as e:
            print(f"异常 {e}")
            results.append((entry, False, time.time() - t0))
            continue
        dt = time.time() - t0
        print(f"{'succeeded' if ok else 'FAILED'}  {dt:.1f}s")
        results.append((entry, ok, dt))

    print("\n" + "=" * 60)
    failed = [r for r in results if not r[1]]
    for entry, ok, dt in results:
        print(f"  {'OK  ' if ok else 'FAIL'}  {entry:24} {dt:6.1f}s")
    print("=" * 60)

    if failed:
        print(f"\n{len(failed)} 个失败。查失败原因：")
        oe = out_dir / "on_error"
        if oe.is_dir() and any(oe.iterdir()):
            print(f"  失败截图：{oe}")
            print("  汇总台账：python tools/failure_ledger.py --screens")
        else:
            print(f"  日志：{out_dir / 'maafw.log'}")
        return 1

    print(f"\n全部成功。调试图：{out_dir}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
