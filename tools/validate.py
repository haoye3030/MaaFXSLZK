# -*- coding: utf-8 -*-
"""一条命令跑完全部校验。

替代手抄这几条：
    python tools/validate_schema.py --schema-dir deps/tools \\
        --resource-dirs assets/resource \\
        --exclude-dirs assets/resource/announcement \\
        --interface-files assets/interface.json
    npx @nekosu/maa-tools check
    python tools/check_assets.py --static

用法：
    python tools/validate.py            # 全部（CI 同款）
    python tools/validate.py --fast     # 跳过 maa-tools（不联网、最快）
    python tools/validate.py --assets   # 额外跑素材检查
    python tools/validate.py --fix-hint # 失败时给出修复提示

退出码：0 = 全过，1 = 有失败。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
TOOLS = PROJECT / "tools"

SCHEMA_CMD = [
    sys.executable,
    str(TOOLS / "validate_schema.py"),
    "--schema-dir", "deps/tools",
    "--resource-dirs", "assets/resource",
    "--exclude-dirs", "assets/resource/announcement",
    "--interface-files", "assets/interface.json",
]


def run(name: str, cmd: list[str], cwd: Path) -> tuple[bool, str]:
    print(f"\n{'=' * 62}\n  {name}\n{'=' * 62}")
    try:
        p = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=600,
        )
    except FileNotFoundError:
        print(f"  [!] 命令不存在：{cmd[0]}")
        return False, "missing"
    except subprocess.TimeoutExpired:
        print("  [!] 超时（600s）")
        return False, "timeout"

    out = (p.stdout or "") + (p.stderr or "")
    print(out.rstrip() if out.strip() else "  (无输出)")
    ok = p.returncode == 0
    print(f"\n  -> {'PASS' if ok else 'FAIL'} (exit {p.returncode})")
    return ok, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="跳过 maa-tools（不联网）")
    ap.add_argument("--assets", action="store_true", help="额外跑素材检查")
    ap.add_argument("--fix-hint", action="store_true", help="失败时给出修复提示")
    args = ap.parse_args()

    results: list[tuple[str, bool, str]] = []

    # 1. JSON Schema（格式合法性）
    ok, out = run("JSON Schema 校验（格式合法性）", SCHEMA_CMD, PROJECT)
    results.append(("JSON Schema", ok, out))

    # 2. maa-tools check（语义合法性）
    if not args.fast:
        npx = shutil.which("npx")
        if npx:
            ok, out = run(
                "maa-tools check（语义合法性）",
                [npx, "--yes", "@nekosu/maa-tools", "check"],
                PROJECT,
            )
            results.append(("maa-tools", ok, out))
        else:
            print("\n[!] 找不到 npx，跳过 maa-tools。装 Node.js 或加 --fast。")
            results.append(("maa-tools", False, "npx not found"))
    else:
        print("\n（--fast：已跳过 maa-tools）")

    # 3. 素材检查（可选）
    if args.assets:
        ok, out = run(
            "素材检查",
            [sys.executable, str(TOOLS / "check_assets.py"), "--static"],
            PROJECT,
        )
        results.append(("素材", ok, out))

    # 汇总
    print(f"\n{'=' * 62}\n  汇总\n{'=' * 62}")
    for name, ok, _ in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    failed = [r for r in results if not r[1]]
    if not failed:
        print("\n全部通过 [OK]")
        return 0

    print(f"\n{len(failed)} 项失败。")

    if args.fix_hint:
        print("\n常见原因：")
        for name, _, out in failed:
            if name == "maa-tools":
                if "load_all_json failed" in out or "duplicate" in out.lower():
                    print("  * JSON 重复键：同一个文件里定义了两次同名节点。"
                          "Maa 会整份加载失败，但 Python 的 json.loads 静默通过。")
                    print("    -> 搜出重复的节点名，删掉一个。")
                elif "Invalid next node name" in out:
                    print("  * next/on_error 指向了不存在的节点，检查拼写。")
                else:
                    print(f"  * maa-tools 报错，往上翻它自己的输出。")
            elif name == "JSON Schema":
                print("  * 字段拼错、类型不对、或用了 schema 里没有的字段。")
                print("    报错里有文件路径和字段名，照着改。")
            elif name == "素材":
                print("  * 按上面 FAIL 列表处理（纯色/缺失/roi 装不下模板）。")
    return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
