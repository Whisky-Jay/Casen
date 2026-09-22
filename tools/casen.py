"""Casen —— 中译英练习，命令行版。

先把「导入 → 翻译 → 评分 → 复习」整个流程跑顺，确认好用再考虑套界面。

    python tools/casen.py import sentences.txt
    python tools/casen.py practice
    python tools/casen.py stats
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows 控制台默认 GBK，中文和制表符会炸。在模块级做，任何入口进来都安全。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import scoring  # noqa: E402
import store  # noqa: E402

DEFAULT_DB = Path(__file__).with_name("casen.db")

# ---------------------------------------------------------------- 终端样式

_TTY = sys.stdout.isatty()


def _sgr(*codes: str) -> str:
    return f"\033[{';'.join(codes)}m" if _TTY else ""


BOLD = _sgr("1")
DIM = _sgr("2")
RED = _sgr("31")
GREEN = _sgr("32")
YELLOW = _sgr("33")
CYAN = _sgr("36")
UNDERLINE = _sgr("4")
RESET = _sgr("0") if _TTY else ""

BAR = "─" * 64


def clear_line() -> None:
    """把当前行擦掉，用来收掉「评分中…」这类临时提示。"""
    print("\r\033[K" if _TTY else "\r", end="", flush=True)


def color_score(n: int) -> str:
    """按分数上色，扫一眼就知道哪项拖后腿。"""
    if n >= 85:
        c = GREEN
    elif n >= 60:
        c = YELLOW
    else:
        c = RED
    return f"{c}{n:3d}{RESET}"


def mark_all(text: str, spans: list[str]) -> str:
    """把多个问题片段标在原句上。重叠的片段只标第一个，不让转义码打架。"""
    intervals: list[tuple[int, int]] = []
    for span in spans:
        if not span:
            continue
        start = 0
        while True:
            i = text.find(span, start)
            if i < 0:
                break
            end = i + len(span)
            if not any(i < b and end > a for a, b in intervals):
                intervals.append((i, end))
                break
            start = i + 1

    if not intervals:
        return text

    intervals.sort()
    out, prev = [], 0
    for a, b in intervals:
        out.append(text[prev:a])
        out.append(f"{RED}{UNDERLINE}{text[a:b]}{RESET}")
        prev = b
    out.append(text[prev:])
    return "".join(out)


# ---------------------------------------------------------------- 子命令

def cmd_import(args) -> int:
    conn = store.connect(args.db)
    items: list[tuple[str, str]] = []
    tag = ""

    for path in args.files:
        text = Path(path).read_text(encoding="utf-8-sig")
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("@"):          # @标签 单独一行，切换后续句子的标签
                tag = line[1:].strip()
                continue
            items.append((line, tag))

    if not items:
        print("没读到任何句子。文件里一行一句中文就行，空行和 # 开头的行会被忽略。")
        return 1

    added, skipped = store.add_sentences(conn, items)
    print(f"新增 {added} 句，跳过 {skipped} 句（已存在）")
    return 0


def cmd_practice(args) -> int:
    conn = store.connect(args.db)
    sentences = store.due_sentences(conn, tag=args.tag, limit=args.limit,
                                    include_future=args.all)

    if not sentences:
        print("今天没有要练的句子。")
        s = store.stats(conn)
        if s["total"] == 0:
            print("先用 import 导入一些中文句子。")
        else:
            print(f"（共 {s['total']} 句，都还没到期。想现在就练加 --all）")
        return 0

    try:
        client = scoring.require_client()
    except scoring.ScoringError as e:
        print(f"{RED}{e}{RESET}", file=sys.stderr)
        return 1

    print(f"\n{BOLD}今天有 {len(sentences)} 句要练。{RESET}"
          f" 输入 {DIM}:q{RESET} 退出，{DIM}:s{RESET} 跳过，直接回车也算跳过。\n")

    usage = scoring.Usage(0, 0)
    done = 0

    for idx, sentence in enumerate(sentences, 1):
        print(BAR)
        print(f"{DIM}[{idx}/{len(sentences)}]{RESET}  {BOLD}{sentence.chinese}{RESET}")
        if sentence.tag:
            print(f"{DIM}标签：{sentence.tag}{RESET}")

        try:
            english = input(f"{CYAN}英文 >{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if english in (":q", ":quit"):
            break
        if not english or english in (":s", ":skip"):
            print(f"{DIM}  跳过{RESET}\n")
            continue

        print(f"{DIM}  评分中…{RESET}", end="\r", flush=True)
        try:
            result, u = scoring.score(sentence.chinese, english,
                                      client=client, effort=args.effort)
        except scoring.ScoringError as e:
            clear_line()
            print(f"  {RED}评分失败：{e}{RESET}\n")
            continue
        clear_line()

        usage = usage + u
        done += 1
        print_result(english, result)

        new_box = store.record_attempt(conn, sentence, english, result)
        due = store.INTERVALS[new_box]
        when = "今天" if due == 0 else f"{due} 天后"
        print(f"{DIM}  盒子 {sentence.box} → {new_box}，{when}再练{RESET}\n")

    print(BAR)
    print(f"练了 {done} 句 | 花费约 ${usage.cost_usd:.4f}")
    return 0


def print_result(english: str, result) -> None:
    s = result.scores

    # 先把所有问题片段标在原句上，逐字定位不到的地方收集起来
    found = [i.span for i in result.issues if i.span and i.span in english]
    unlocated = [i.span for i in result.issues if not (i.span and i.span in english)]

    print(f"\n  {CYAN}▸{RESET} {mark_all(english, found)}")
    print(f"    语义 {color_score(s.meaning)}   语法 {color_score(s.grammar)}   "
          f"自然度 {color_score(s.naturalness)}   用词 {color_score(s.vocabulary)}"
          f"   {BOLD}→ {result.overall}{RESET}")

    if result.issues:
        print(f"\n  {BOLD}问题{RESET}")
        for issue in result.issues:
            print(f"    · {issue.explain}")
            print(f"      {DIM}[{issue.type}] {issue.span}{RESET}")
        if unlocated:
            # span 定位不到，说明模型没照规矩逐字摘抄 —— prompt 得改
            print(f"\n    {YELLOW}注意：以下片段在译文里找不到，无法定位到原句上"
                  f"（prompt 输出不规范）：{'、'.join(unlocated)}{RESET}")

    print(f"\n  {GREEN}参考{RESET}  {result.reference}")
    if result.also_acceptable:
        print(f"  {GREEN}也可{RESET}  {'  /  '.join(result.also_acceptable)}")
    print(f"\n  {DIM}{result.comment}{RESET}")


def cmd_stats(args) -> int:
    conn = store.connect(args.db)
    s = store.stats(conn)

    if s["total"] == 0:
        print("还没有句子。用 import 导入。")
        return 0

    print(f"\n{BOLD}句子库{RESET}")
    print(f"  总数 {s['total']}   练过 {s['practiced']}   "
          f"没练过 {s['total'] - s['practiced']}   今天到期 {s['due']}")
    print(f"  累计练习 {s['attempts']} 次")

    if s["attempts"]:
        print(f"\n{BOLD}最近 100 次的平均分{RESET}")
        avg = s["avg"]
        print(f"  总分 {color_score(round(avg['overall']))}")
        for key, label in (("meaning", "语义"), ("grammar", "语法"),
                           ("naturalness", "自然度"), ("vocabulary", "用词")):
            print(f"  {label:<4} {color_score(round(avg[key]))}")

        weakest = min(("meaning", "grammar", "naturalness", "vocabulary"),
                      key=lambda k: avg[k])
        cn = {"meaning": "语义", "grammar": "语法",
              "naturalness": "自然度", "vocabulary": "用词"}[weakest]
        print(f"\n  {YELLOW}最薄弱的维度是「{cn}」，下一步可以重点盯这个。{RESET}")

    tags = store.all_tags(conn)
    if tags:
        print(f"\n{BOLD}标签{RESET}")
        for tag, n in tags:
            print(f"  {tag or '(无标签)':<12} {n} 句")
    return 0


def cmd_weak(args) -> int:
    conn = store.connect(args.db)
    rows = store.weak_sentences(conn, limit=args.limit)
    if not rows:
        print("还没有练习记录。")
        return 0

    print(f"\n{BOLD}最需要重练的 {len(rows)} 句{RESET}\n")
    for row in rows:
        print(f"  {color_score(row['overall'])}  {row['chinese']}")
        print(f"       {DIM}语法 {row['grammar']} · 最近 {row['last_at']}{RESET}")
    return 0


# ---------------------------------------------------------------- 入口

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="casen", description="中译英练习：导入中文句子，自己翻，AI 评分。")
    parser.add_argument("--db", default=str(DEFAULT_DB),
                        help="句子库文件（默认 tools/casen.db）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import", help="导入中文句子（一行一句，@标签 单独一行切标签）")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("practice", help="练今天到期的句子")
    p.add_argument("--tag", help="只练某个标签")
    p.add_argument("--limit", type=int, help="最多练几句")
    p.add_argument("--all", action="store_true", help="不管到期没到期，全都拿出来练")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                   help="模型思考深度，默认 high。调低可以省钱")
    p.set_defaults(func=cmd_practice)

    p = sub.add_parser("stats", help="看看整体情况")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("weak", help="列出最需要重练的句子")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_weak)

    args = parser.parse_args()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n已退出。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
