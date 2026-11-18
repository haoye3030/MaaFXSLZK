# -*- coding: utf-8 -*-
"""MaaFXSLZK 自定义识别扩展（AgentServer 入口）。

由 interface.json 的 agent 字段拉起：
    child_exec = E:\\DSH\\MaaFX\\agent-venv\\Scripts\\python.exe（maafw 5.10.0，协议 v7）
    child_args = ["agent/main.py"]
MFAAvalonia / MaaPiCli 会自动传入 socket_id 作为最后一个参数。

协议版本必须与客户端匹配（见 recognizers.py 顶部说明），
5.10 客户端（MFAAvalonia v2.16.4）只能连 5.10.x 的 AgentServer。
"""
import sys

from maa.agent.agent_server import AgentServer

from recognizers import ExpIsNightWindow, ExpTimeCheck


def main():
    if len(sys.argv) < 2:
        print("Usage: python agent/main.py <socket_id>", file=sys.stderr)
        sys.exit(1)
    socket_id = sys.argv[-1]
    AgentServer.register_custom_recognition("ExpTimeCheck", ExpTimeCheck())
    AgentServer.register_custom_recognition("ExpIsNightWindow", ExpIsNightWindow())
    AgentServer.start_up(socket_id)
    AgentServer.join()
    AgentServer.shut_down()


if __name__ == "__main__":
    main()
