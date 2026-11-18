# -*- coding: utf-8 -*-
"""校验 agent 运行时与 MFAAvalonia 内置 MaaFramework 的版本配对。

背景（2026-11-19 实测）：
- MFAAvalonia v2.16.4 的 C# 绑定层 libs/MaaFramework.Binding.Native.dll 的 FileVersion 是
  5.10.0.0，但真正跑的是 runtimes/win-x64/native/MaaFramework.dll（v5.16.1）。
- Agent 协议不跨版本兼容：agent 子进程（E:\\DSH\\MaaFX\\agent-venv 里的 maafw）必须与客户端
  同版本，否则 MFAAvalonia 只显示「Agent 连接重试（2/3)」，日志里是
  Protocol version mismatch client: [req.version=...][req.protocol=N] server: [...]。
- 升级 MFAAvalonia 或改 agent venv 后先跑这条命令，比等「Agent 连接重试」再翻日志快得多。

用法：
    python tools/check_agent_env.py            # 人类可读结论
    python tools/check_agent_env.py --json     # 机器可读
退出码：0 配对一致 / 1 不一致 / 2 环境缺失（release 未同步等）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
RELEASE = PROJECT.parent / "release" / "win-x64"
NATIVE_DLL = RELEASE / "runtimes" / "win-x64" / "native" / "MaaFramework.dll"
AGENT_VENV = Path(r"E:\DSH\MaaFX\agent-venv")


def _norm(v: str) -> str:
    v = v.strip()
    return v if v.startswith("v") else "v" + v


def _key(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def client_version():
    """从 release 里真正的原生库提取版本（唯一可信来源）。"""
    if not NATIVE_DLL.exists():
        return None
    raw = NATIVE_DLL.read_bytes()
    hits = {m.group(0) for m in re.finditer(rb"v\d{1,2}\.\d{1,2}\.\d{1,2}", raw)}
    if not hits:
        return None
    versions = sorted((h.decode() for h in hits), key=_key)
    return _norm(versions[-1])


def _dist_version(site_packages: Path):
    """直接从 dist-info/METADATA 读版本，避免起子进程。"""
    if not site_packages.exists():
        return None
    for meta in site_packages.glob("maafw-*.dist-info/METADATA"):
        for line in meta.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Version:"):
                return _norm(line.split(":", 1)[1].strip())
    return None


def agent_version():
    return _dist_version(AGENT_VENV / "Lib" / "site-packages")


def system_version():
    """系统 python 的 maafw（tools/run_task.py 的进程内注册路径用）。"""
    try:
        out = subprocess.run(
            [sys.executable, "-c",
             "from maa.library import Library; print(Library.version())"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception:
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("v"):
            return _norm(line)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    client = client_version()
    agent = agent_version()
    system = system_version()
    ok = client is not None and agent is not None and _key(client) == _key(agent)

    if args.json:
        print(json.dumps({
            "client_native_dll": str(NATIVE_DLL),
            "client_maafw": client,
            "agent_venv": str(AGENT_VENV),
            "agent_maafw": agent,
            "system_python_maafw": system,
            "paired": ok,
        }, ensure_ascii=False, indent=2))
    else:
        print("MFAAvalonia 内置 MaaFramework : " + (client or "<release 未同步，找不到原生库>"))
        print("agent venv maafw              : " + (agent or "<venv 未安装 maafw>"))
        print("系统 python maafw（仅 run_task.py 进程内用）: " + (system or "<未安装>"))
        if client is None:
            print("")
            print("[SKIP] 找不到 release 原生库：先跑 ..\\sync_resource.bat")
        elif ok:
            print("")
            print("[OK] 版本配对一致（" + client + "），agent 子进程可以握手。")
        else:
            print("")
            print("[FAIL] 版本不匹配：客户端 " + str(client) + " vs agent venv " + str(agent))
            print("  修复：& " + str(AGENT_VENV) + "\\Scripts\\python.exe -m pip install --force-reinstall maafw==" + client.lstrip("v"))
            print("  （装之前先关掉 MFAAvalonia，否则 directml.dll 被 agent 子进程占用会 WinError 5）")
    if client is None:
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

