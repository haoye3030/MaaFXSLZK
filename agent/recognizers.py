# -*- coding: utf-8 -*-
"""远征时间约束识别器（纯逻辑，不注册）。

由 agent/main.py 通过 AgentServer.register_custom_recognition 注册（agent 进程模式），
或由 tools/run_task.py 通过 Resource.register_custom_recognition 注册（进程内模式）。

协议版本约束（2026-11-19 复核，纠正 11-18 的错误结论）：
- MFAAvalonia v2.16.4 实际加载的原生库是 MaaFramework 5.16.1（Agent 协议 v8），版本串内嵌在
  E:\\DSH\\MaaFX\\release\\win-x64\\runtimes\\win-x64\\native\\MaaFramework.dll；
  libs\\MaaFramework.Binding.Native.dll 的 FileVersion 5.10.0.0 只是 C# 绑定层版本，会误导。
- Agent 协议不跨版本兼容：5.10 的 AgentServer 直接拒掉 5.16 客户端（Protocol version mismatch
  7 vs 8），表现为 MFAAvalonia 一直显示「Agent 连接重试」。
- 因此 agent venv（E:\\DSH\\MaaFX\\agent-venv）必须装与客户端同版本的 maafw（现 v5.16.1），
  interface.json 的 child_exec 指向该 venv 的 python.exe；配对检查跑
  python tools/check_agent_env.py。

custom_recognition_param 在两种路径下的形态：
- 进程内：裸 JSON 字符串，如 {"latest_done":"23:00"}
- agent：整体 JSON 序列化后未反序列化的带引号转义串（可能双层），
  _parse_param 会尝试最多 3 层 json.loads 并容忍任何失败。

analyze 内任何异常都会被 ctypes 回调吞掉且默认按「识别成功」处理，
因此 analyze 永不抛异常，任何异常路径显式返回 box=None（走 on_error）。
"""
import json
from datetime import datetime, timedelta

from maa.context import Context
from maa.custom_recognition import CustomRecognition

FULL_SCREEN = (0, 0, 1280, 720)


def _parse_param(raw) -> dict:
    """把 custom_recognition_param 解析为 dict，容忍多层 JSON 包裹，永不抛异常。"""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str) or not raw.strip():
        return {}
    val = raw
    for _ in range(3):
        try:
            val = json.loads(val)
        except Exception:
            break
        if isinstance(val, dict):
            return val
        if not isinstance(val, str):
            break
    return {}


def _parse_hhmm(s: str, now: datetime) -> datetime:
    hh, mm = s.strip().split(":")
    return now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)


class ExpTimeCheck(CustomRecognition):
    """时间约束检查：判断「当前时刻 + 任务时长 ≤ 最晚完成时刻」。

    custom_recognition_param（JSON）：
        {"latest_done": "23:00", "duration_hours": 8}
    - latest_done: 最晚完成时刻，格式 HH:MM（默认 23:00）
    - duration_hours: 任务时长（小时），用于计算完成时刻

    返回：命中（box 全屏）表示「可派」；None 表示「会超时，跳过」。
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult:
        try:
            return self._do_analyze(argv)
        except Exception as e:
            print(
                f"[CUSTOM-RECO] name={argv.custom_recognition_name} ERROR: {e!r} "
                f"param={argv.custom_recognition_param!r}",
                flush=True,
            )
            return CustomRecognition.AnalyzeResult(
                box=None, detail={"error": repr(e)}
            )

    def _do_analyze(
        self, argv: CustomRecognition.AnalyzeArg
    ) -> CustomRecognition.AnalyzeResult:
        param = _parse_param(argv.custom_recognition_param)
        latest_done = str(param.get("latest_done", "23:00"))
        duration_hours = float(param.get("duration_hours", 8))

        now = datetime.now()
        done_at = now + timedelta(hours=duration_hours)
        latest = _parse_hhmm(latest_done, now)

        ok = done_at <= latest
        print(
            f"[CUSTOM-RECO] name={argv.custom_recognition_name} "
            f"now={now.strftime('%H:%M')} done={done_at.strftime('%H:%M')} "
            f"latest={latest.strftime('%H:%M')} ok={ok}",
            flush=True,
        )
        if ok:
            return CustomRecognition.AnalyzeResult(
                box=FULL_SCREEN,
                detail={
                    "now": now.strftime("%H:%M"),
                    "done_at": done_at.strftime("%H:%M"),
                    "latest": latest.strftime("%H:%M"),
                    "ok": True,
                },
            )
        return CustomRecognition.AnalyzeResult(
            box=None,
            detail={
                "now": now.strftime("%H:%M"),
                "done_at": done_at.strftime("%H:%M"),
                "latest": latest.strftime("%H:%M"),
                "ok": False,
            },
        )


class ExpIsNightWindow(CustomRecognition):
    """判断当前是否在限时远征窗口（默认 18:00 ~ 23:59）。

    custom_recognition_param（JSON，可选）：
        {"start": "18:00", "end": "23:59"}
    若 start > end 视为跨午夜窗口（如 22:00~02:00）。

    返回：命中 = 在窗口内；None = 不在。
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult:
        try:
            return self._do_analyze(argv)
        except Exception as e:
            print(
                f"[CUSTOM-RECO] name={argv.custom_recognition_name} ERROR: {e!r} "
                f"param={argv.custom_recognition_param!r}",
                flush=True,
            )
            return CustomRecognition.AnalyzeResult(
                box=None, detail={"error": repr(e)}
            )

    def _do_analyze(
        self, argv: CustomRecognition.AnalyzeArg
    ) -> CustomRecognition.AnalyzeResult:
        param = _parse_param(argv.custom_recognition_param)
        start_s = str(param.get("start", "18:00"))
        end_s = str(param.get("end", "23:59"))

        now = datetime.now()
        start = _parse_hhmm(start_s, now)
        end = _parse_hhmm(end_s, now)

        if start <= end:
            ok = start <= now <= end
        else:  # 跨午夜窗口
            ok = now >= start or now <= end
        print(
            f"[CUSTOM-RECO] name={argv.custom_recognition_name} "
            f"now={now.strftime('%H:%M')} in_window={ok}",
            flush=True,
        )
        if ok:
            return CustomRecognition.AnalyzeResult(
                box=FULL_SCREEN,
                detail={"now": now.strftime("%H:%M"), "in_window": True},
            )
        return CustomRecognition.AnalyzeResult(
            box=None,
            detail={"now": now.strftime("%H:%M"), "in_window": False},
        )
