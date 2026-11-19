# -*- coding: utf-8 -*-
r"""咨询中心答题识别器（纯逻辑，不注册）。

由 agent/main.py 通过 AgentServer.register_custom_recognition 注册（agent 进程模式），
或由 tools/run_task.py 通过 Resource.register_custom_recognition 注册（进程内模式）。
题库数据在 agent/quiz_bank.py（由 tools/gen_quiz_bank.py 从 docs/quiz-bank.md 生成）。

协议约束（与 recognizers.py 相同，2026-11-19 复核）：
- 客户端原生库是 MaaFramework 5.16.1（Agent 协议 v8），agent venv
  E:\DSH\MaaFX\agent-venv 必须装同版本 maafw；配对检查 python tools/check_agent_env.py。
- custom_recognition_param 在 agent 路径下可能是多层 JSON 包裹的字符串，_parse_param 容忍 1~3 层。
- analyze 内任何异常都会被 ctypes 回调吞掉且默认按「识别成功」处理，因此 analyze 永不抛异常，
  异常路径显式返回 box=None（走 on_error）。
- run_recognition_direct 走 agent RPC，已实测可用（tmp/agent_e2e_ocr.py）。

两个识别器：
- QuizAnswer：题目界面 OCR 题干 + 选项 → 查题库 → 返回正确选项文字的 box
  （pipeline 用 Click + target=true 点该 box 中心即点中选项按钮）。
  帮助页原文「回答错误，不扣减好感度」→ 题库未命中时兜底选第一个选项，不浪费答题机会。
- QuizGirl：房间内 OCR 好感标签 + 模板匹配「?」徽章 → 返回某个舰灵的点击 box。
  记住本轮已点过的坐标（TTL 默认 900s），避免点到空处后在同一个标签上无限重复；
  正常情况下答完题舰灵会整屋消失，所以这个去重只在异常路径起作用。
"""
import json
import re
import time
import unicodedata
from difflib import SequenceMatcher

from maa.context import Context
from maa.custom_recognition import CustomRecognition
from maa.pipeline import JOCR, JRecognitionType, JTemplateMatch

from quiz_bank import QUIZ_BANK

FULL_SCREEN = (0, 0, 1280, 720)
# 题目界面（E:\DSH\MaaFX\tmp\quiz_out\42_tap_640_600.png 实测）：
# 题干单行 box (232,649,556,34)；说话人名在 y<=614，故题干 ROI 从 630 起，避开人名
DEFAULT_QUESTION_ROI = (200, 630, 900, 90)
# 选项是 3 条横向按钮（x 265..1015），文字居中 x~637，实测 3 条时 y 中心 208/305/403
DEFAULT_OPTION_ROI = (240, 120, 820, 420)
# 选项条几何（结构校验）：3~4 条按钮的文字框中心 x≈637、y 中心 208/305/403（第 4 条 ~501），
# 相邻条间距 ~98px。用它把「VN 对话/房间好感标签/帮助页说明」这类被 option_roi 顺带抓到的
# 零散文字挡掉——否则自定义识别器会在对话页凑出 2 条噪声“选项”并兜底乱点。
OPTION_CENTER_X = 637.0
OPTION_CX_TOL = 80.0
OPTION_CY_MIN = 150.0
OPTION_CY_MAX = 560.0
OPTION_GAP_MIN = 70.0
OPTION_GAP_MAX = 130.0
# 房间内舰灵/标签区域：避开顶部按钮栏(y<=80)与右下角刷新面板(y>=565)
DEFAULT_ROOM_ROI = (20, 100, 1240, 520)

# 好感标签（咨询中心舰灵头顶浮标）。匹配用「归一化后包含」以容忍 OCR 多字/少字。
# 好感阶段阶梯（赠礼页/房间里显示的 6 级，从低到高）
STAGES = ("陌生", "相识", "亲近", "依偎", "誓约", "永恒")
LOVE_LABELS = STAGES + ("恋慕", "挚爱", "亲密", "爱慕")
LOVE_LABEL_RE = ".*(" + "|".join(LOVE_LABELS) + ").*"

_NORM_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


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


def _rect(raw, default):
    try:
        if isinstance(raw, (list, tuple)) and len(raw) == 4:
            return tuple(int(float(v)) for v in raw)
    except Exception:
        pass
    return tuple(default)


def norm(s: str) -> str:
    """归一化文本：全角转半角、小写、去掉所有标点/括号/空白。

    例：「「Big Seven」」与「[Big Seven]」都归一为 bigseven。
    """
    s = unicodedata.normalize("NFKC", s or "").lower()
    return _NORM_RE.sub("", s)


def _ocr(context: Context, image, roi, threshold=0.3, expected=None):
    """跑一次直连 OCR，返回结果项列表（永不抛异常，失败返回空列表）。"""
    param = JOCR(expected=list(expected or []), roi=tuple(roi), threshold=threshold)
    detail = context.run_recognition_direct(JRecognitionType.OCR, param, image)
    return list(getattr(detail, "all_results", None) or [])


def _sorted_items(items, min_score, min_len=1):
    """按 (y 中心, x) 排序，过滤低分/空文本。"""
    out = []
    for it in items:
        text = (getattr(it, "text", "") or "").strip()
        score = float(getattr(it, "score", 0.0) or 0.0)
        box = getattr(it, "box", None)
        if not text or len(text) < min_len or not box or score < min_score:
            continue
        out.append(it)
    out.sort(key=lambda it: (it.box[1] + it.box[3] / 2.0, it.box[0]))
    return out


def _join_items(items) -> str:
    return "".join((it.text or "").strip() for it in items)


def match_question(question: str, limit: int = 3, min_score: float = 0.6):
    """题干模糊匹配题库，返回 [(相似度, 题目, 答案), ...] 按相似度降序。"""
    nq = norm(question)
    if not nq:
        return []
    scored = []
    for q, a in QUIZ_BANK:
        ratio = SequenceMatcher(None, norm(q), nq).ratio()
        if ratio >= min_score:
            scored.append((ratio, q, a))
    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


def choose_option(options, answer: str, min_score: float = 0.75):
    """在选项里挑出与答案最匹配的一条，返回 (索引, 相似度)；无可用项时索引为 None。"""
    na = norm(answer)
    if not na:
        return None, 0.0
    best_idx, best_score = None, 0.0
    for i, it in enumerate(options):
        no = norm(getattr(it, "text", ""))
        if not no:
            continue
        if no == na:
            return i, 1.0
        score = 0.0
        # 包含关系只在「两边都不短、且不是纯数字」时才算强匹配，
        # 否则 460 会误配 46、4个 会误配 4。
        if len(na) >= 2 and len(no) >= 2 and not (na.isdigit() and no.isdigit()):
            if na in no or no in na:
                score = 0.95
        if score <= 0.0:
            score = SequenceMatcher(None, na, no).ratio()
        if score > best_score:
            best_idx, best_score = i, score
    if best_idx is not None and best_score >= min_score:
        return best_idx, best_score
    return None, best_score


def _box_center(box):
    x, y, w, h = box
    return x + w / 2.0, y + h / 2.0


def _looks_like_option_rows(options):
    """校验 OCR 结果是否构成题目界面的那 2~4 条横向选项按钮。

    返回 (bool, reason)。判定条件（全部来自实机截图 42_tap_640_600.png）：
      * 条数 2~4；
      * 每条文字框中心 x 落在 637±80、y 落在 [150, 560]；
      * 按 y 排序后相邻间距在 [70, 130]。
    不满足即认为当前不是题目界面（VN 对话页/房间/帮助页都会失败），
    让 pipeline 落到 QuizAdvance 继续推进，而不是乱点选项。
    """
    n = len(options)
    if not 2 <= n <= 4:
        return False, f"count={n}"
    centers = []
    for it in options:
        box = getattr(it, "box", None)
        if not box:
            return False, "no_box"
        centers.append(_box_center(box))
    for cx, cy in centers:
        if abs(cx - OPTION_CENTER_X) > OPTION_CX_TOL:
            return False, f"cx={cx:.0f} off"
        if not OPTION_CY_MIN <= cy <= OPTION_CY_MAX:
            return False, f"cy={cy:.0f} off"
    ys = sorted(cy for _, cy in centers)
    gaps = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
    for g in gaps:
        if not OPTION_GAP_MIN <= g <= OPTION_GAP_MAX:
            return False, f"gap={g:.0f}"
    return True, "ok"


class QuizAnswer(CustomRecognition):
    """题目界面识别 + 选答案。

    custom_recognition_param（JSON，全部可选）：
        {
          "question_roi": [200, 630, 900, 90],
          "option_roi": [240, 120, 820, 420],
          "question_threshold": 0.6,
          "option_threshold": 0.75
        }
    返回：正确选项文字的 box（命中）；None（不是题目界面 / 没有选项）。
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult:
        try:
            return self._do_analyze(context, argv)
        except Exception as e:
            print(
                f"[CUSTOM-RECO] name={argv.custom_recognition_name} ERROR: {e!r} "
                f"param={argv.custom_recognition_param!r}",
                flush=True,
            )
            return CustomRecognition.AnalyzeResult(box=None, detail={"error": repr(e)})

    def _do_analyze(
        self, context: Context, argv: CustomRecognition.AnalyzeArg
    ) -> CustomRecognition.AnalyzeResult:
        param = _parse_param(argv.custom_recognition_param)
        q_roi = _rect(param.get("question_roi"), DEFAULT_QUESTION_ROI)
        o_roi = _rect(param.get("option_roi"), DEFAULT_OPTION_ROI)
        q_thr = float(param.get("question_threshold", 0.6))
        o_thr = float(param.get("option_threshold", 0.75))

        question = _join_items(_sorted_items(_ocr(context, argv.image, q_roi), 0.5))
        options = _sorted_items(_ocr(context, argv.image, o_roi), 0.6)
        # 真题目界面固定是 3~4 条等距横向按钮；条数不对或几何不像（VN 对话页、
        # 房间好感标签、帮助页说明等等被 option_roi 顺带抓进来）一律不作答，
        # 宁可不作答也不要乱点——失败会落到 QuizAdvance 推进对话。
        ok, why = _looks_like_option_rows(options)
        if not ok:
            print(
                f"[CUSTOM-RECO] name={argv.custom_recognition_name} "
                f"bad_options question={question!r} n={len(options)} why={why}",
                flush=True,
            )
            return CustomRecognition.AnalyzeResult(
                box=None,
                detail={
                    "reason": "bad_options",
                    "question": question,
                    "n": len(options),
                    "why": why,
                },
            )

        cands = match_question(question, limit=3, min_score=q_thr)
        picked_idx, picked_q, picked_a = None, "", ""
        picked_qscore, picked_oscore = 0.0, 0.0
        for qscore, q, a in cands:
            idx, oscore = choose_option(options, a, o_thr)
            if idx is not None:
                picked_idx, picked_q, picked_a = idx, q, a
                picked_qscore, picked_oscore = qscore, oscore
                break

        fallback = picked_idx is None
        if fallback:
            # 题库没命中或答案匹配不上选项 → 兜底选第一个选项（答错不扣好感度）
            picked_idx = 0
            if cands:
                picked_qscore, picked_q, picked_a = cands[0]

        box = tuple(int(v) for v in options[picked_idx].box)
        detail = {
            "question": question,
            "question_matched": picked_q,
            "answer": picked_a,
            "question_score": round(picked_qscore, 4),
            "option_score": round(picked_oscore, 4),
            "options": [it.text for it in options],
            "picked_index": picked_idx,
            "picked_text": options[picked_idx].text,
            "fallback": fallback,
        }
        print(
            f"[CUSTOM-RECO] name={argv.custom_recognition_name} "
            f"q={question[:40]!r} match={picked_q[:20]!r}({picked_qscore:.3f}) "
            f"answer={picked_a!r} opts={detail['options']} "
            f"pick={detail['picked_text']!r} fallback={fallback}",
            flush=True,
        )
        return CustomRecognition.AnalyzeResult(box=box, detail=detail)


class QuizGirl(CustomRecognition):
    """房间内挑一个可交互舰灵并给出点击点。

    custom_recognition_param（JSON，全部可选）：
        {
          "room_roi": [20, 100, 1240, 520],
          "click_dx": -25, "click_dy": 95,      # 好感标签中心 → 舰灵点击点
          "badge_dx": -27, "badge_dy": 112,     # 「?」徽章中心 → 舰灵点击点
          "badge_template": "quiz/quiz_mark.png",
          "badge_threshold": 0.8,
          "dedupe_radius": 70,
          "state_ttl_sec": 900,
          "labels": null,      # null=任意阶段（含「?」徽章）；[]=本节点关闭；
                               # 或 ["誓约"] 只挑该阶段的舰灵
          "badge": null        # labels 缺省时默认 true（纳入「?」徽章舰灵）
        }
    返回：点击点的小 box（命中）；None（房间里没有可交互舰灵）。
    多个 pipeline 节点共用同一个 QuizGirl 实例，_used 去重是跨节点共享的。
    """

    def __init__(self):
        super().__init__()
        self._used = []  # [(时间戳, x, y)]

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult:
        try:
            return self._do_analyze(context, argv)
        except Exception as e:
            print(
                f"[CUSTOM-RECO] name={argv.custom_recognition_name} ERROR: {e!r} "
                f"param={argv.custom_recognition_param!r}",
                flush=True,
            )
            return CustomRecognition.AnalyzeResult(box=None, detail={"error": repr(e)})

    def _candidates(self, context, argv, param, room_roi, ttl):
        points = []

        # 按好感阶段过滤：labels 缺省 = 全部阶段；labels=[] = 一个都不要（节点关闭）
        raw_labels = param.get("labels", None)
        allowed = LOVE_LABELS if raw_labels is None else tuple(str(x) for x in raw_labels)
        # 「?」徽章（看不到好感标签的舰灵）只在 labels 缺省时默认纳入
        want_badge = bool(param.get("badge", raw_labels is None))
        if not allowed:
            return points

        # 1) 好感标签
        items = _ocr(
            context, argv.image, room_roi, threshold=0.3, expected=[LOVE_LABEL_RE]
        )
        dx = float(param.get("click_dx", -25))
        dy = float(param.get("click_dy", 95))
        for it in _sorted_items(items, 0.6):
            text = norm(it.text)
            if not any(norm(lab) in text for lab in allowed):
                continue
            cx, cy = _box_center(it.box)
            points.append((cx + dx, cy + dy, f"label:{it.text}"))

        # 2) 「?」徽章（无好感标签的舰灵就靠它）
        if not want_badge:
            points.sort(key=lambda p: (p[1], p[0]))
            return points
        tpl = param.get("badge_template") or "quiz/quiz_mark.png"
        try:
            tpl_param = JTemplateMatch(
                template=[tpl],
                roi=tuple(room_roi),
                threshold=[float(param.get("badge_threshold", 0.8))],
            )
            detail = context.run_recognition_direct(
                JRecognitionType.TemplateMatch, tpl_param, argv.image
            )
            # 注意：直连识别即使未达阈值也会返回 best_result，必须先看 hit
            best = None
            if getattr(detail, "hit", False):
                best = getattr(detail, "best_result", None)
                if best is None and getattr(detail, "all_results", None):
                    best = detail.all_results[0]
            if best is not None and getattr(best, "box", None):
                bx, by = _box_center(best.box)
                points.append(
                    (
                        bx + float(param.get("badge_dx", -27)),
                        by + float(param.get("badge_dy", 112)),
                        f"badge:{float(getattr(best, 'score', 0.0)):.3f}",
                    )
                )
        except Exception as e:  # 模板缺失/不匹配不应影响标签路径
            print(f"[CUSTOM-RECO] badge match skipped: {e!r}", flush=True)

        points.sort(key=lambda p: (p[1], p[0]))
        return points

    def _do_analyze(
        self, context: Context, argv: CustomRecognition.AnalyzeArg
    ) -> CustomRecognition.AnalyzeResult:
        param = _parse_param(argv.custom_recognition_param)
        room_roi = _rect(param.get("room_roi"), DEFAULT_ROOM_ROI)
        ttl = float(param.get("state_ttl_sec", 900))
        radius = float(param.get("dedupe_radius", 70))

        now = time.time()
        self._used = [u for u in self._used if now - u[0] <= ttl]

        points = self._candidates(context, argv, param, room_roi, ttl)
        if not points:
            # 注意：这里不清 _used —— 多阶段节点共用同一实例，
            # 某个阶段节点找不到人会误导「房间空」的判定，清空会破坏去重。
            # 状态靠 state_ttl_sec 自然过期。
            print(
                f"[CUSTOM-RECO] name={argv.custom_recognition_name} no_girl",
                flush=True,
            )
            return CustomRecognition.AnalyzeResult(
                box=None, detail={"reason": "no_girl"}
            )

        chosen = None
        for px, py, src in points:
            if any((px - ux) ** 2 + (py - uy) ** 2 <= radius * radius for _, ux, uy in self._used):
                continue
            chosen = (px, py, src)
            break

        if chosen is None:
            print(
                f"[CUSTOM-RECO] name={argv.custom_recognition_name} "
                f"all_used n={len(points)} used={len(self._used)}",
                flush=True,
            )
            return CustomRecognition.AnalyzeResult(
                box=None, detail={"reason": "all_used", "points": len(points)}
            )

        px, py, src = chosen
        self._used.append((now, px, py))
        box = (int(px) - 1, int(py) - 1, 3, 3)
        detail = {
            "click": [int(px), int(py)],
            "source": src,
            "candidates": [p[2] for p in points],
        }
        print(
            f"[CUSTOM-RECO] name={argv.custom_recognition_name} "
            f"click=({int(px)},{int(py)}) src={src} "
            f"cands={detail['candidates']} used={len(self._used)}",
            flush=True,
        )
        return CustomRecognition.AnalyzeResult(box=box, detail=detail)
