# -*- coding: utf-8 -*-
r"""从 docs/quiz-bank.md 生成 agent/quiz_bank.py（答题题库纯数据模块）。

用法规约：
- docs/quiz-bank.md 是题库唯一真源（人工维护），改完必须重跑本脚本：
    python tools/gen_quiz_bank.py
- agent 进程以 release 根为 CWD，读不到 docs/，所以题库必须以 .py 形式随 agent 同步；
  sync_resource.bat 的 robocopy agent\*.py 会自动带上生成文件。

清洗规则（写死在 clean_text）：
- 去掉 Markdown 粗体 **...**
- 去掉中文括号补充说明 （...） —— 题库里的「（游戏内已改…）」「（新规则）」都是备注，不是题面/答案
- 缺号行（#61）与空题面跳过

output: agent/quiz_bank.py 内 QUIZ_BANK = [(题目, 答案), ...]
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "quiz-bank.md"
DST = ROOT / "agent" / "quiz_bank.py"

ROW_RE = re.compile(r"^\|\s*([0-9]+[ab]?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")
COMMENT_RE = re.compile(r"（[^）]*）|\([^)]*\)")


def clean_text(s: str) -> str:
    s = s.replace("**", "")
    s = COMMENT_RE.sub("", s)
    return s.strip()


def main() -> int:
    rows = []
    for line in SRC.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        num, question, answer = m.groups()
        question = clean_text(question)
        answer = clean_text(answer)
        if not question or not answer:
            print(f"skip #{num}: empty question/answer", flush=True)
            continue
        if answer.startswith("—") or answer.startswith("-"):
            print(f"skip #{num}: placeholder answer {answer!r}", flush=True)
            continue
        rows.append((num, question, answer))

    lines = [
        "# -*- coding: utf-8 -*-",
        '"""答题题库（由 tools/gen_quiz_bank.py 从 docs/quiz-bank.md 生成，请勿手改）。',
        "",
        f"共 {len(rows)} 题。改题库请编辑 docs/quiz-bank.md 后重跑：",
        "    python tools/gen_quiz_bank.py",
        '"""',
        "",
        "QUIZ_BANK = [",
    ]
    for num, q, a in rows:
        lines.append(f"    # {num}")
        lines.append(f"    ({q!r}, {a!r}),")
    lines.append("]")
    lines.append("")
    DST.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {DST} rows={len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
