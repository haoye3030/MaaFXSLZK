# -*- coding: utf-8 -*-
r"""MaaFXSLZK 自定义识别扩展（AgentServer 入口）。

由 interface.json 的 agent 字段拉起：
    child_exec = E:\DSH\MaaFX\agent-venv\Scripts\python.exe（maafw 必须与客户端同版本）
    child_args = ["agent/main.py"]
MFAAvalonia / MaaPiCli 会自动传入 socket_id 作为最后一个参数。

Agent 协议不跨版本兼容（2026-11-19 复核）：客户端版本看
E:\DSH\MaaFX\release\win-x64\runtimes\win-x64\native\MaaFramework.dll 里内嵌的版本串
（v2.16.4 实测是 v5.16.1 / 协议 8）；libs/MaaFramework.Binding.Native.dll 的 FileVersion
5.10.0.0 只是 C# 绑定层，会误导。配对检查：python tools/check_agent_env.py。
"""
import os
import sys

from maa.agent.agent_server import AgentServer
from maa.library import Library

from quiz import QuizAnswer, QuizGirl
from recognizers import ExpIsNightWindow, ExpTimeCheck


def main():
    if len(sys.argv) < 2:
        print("Usage: python agent/main.py <socket_id>", file=sys.stderr)
        sys.exit(1)
    socket_id = sys.argv[-1]
    server_version = Library.version()
    print("[agent] maafw " + server_version + " pid=" + str(os.getpid()) + " socket=" + socket_id,
          flush=True)
    AgentServer.register_custom_recognition("ExpTimeCheck", ExpTimeCheck())
    AgentServer.register_custom_recognition("ExpIsNightWindow", ExpIsNightWindow())
    AgentServer.register_custom_recognition("QuizAnswer", QuizAnswer())
    AgentServer.register_custom_recognition("QuizGirl", QuizGirl())
    if not AgentServer.start_up(socket_id):
        # 最常见原因：协议版本不匹配（客户端升级了，venv 还是旧 maafw）。
        print("[agent] start_up 失败：本进程 maafw=" + server_version +
              "，客户端原生库版本必须完全相同。"
              "先跑 python tools/check_agent_env.py，再按提示把 agent-venv 重装成客户端版本。",
              flush=True)
        sys.exit(2)
    AgentServer.join()
    AgentServer.shut_down()


if __name__ == "__main__":
    main()

