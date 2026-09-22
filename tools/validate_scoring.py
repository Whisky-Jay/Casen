"""跑一遍评分 prompt，人工检查输出是否合理。

用法：
    export ANTHROPIC_API_KEY=sk-ant-...
    python tools/validate_scoring.py            # 全部 30 条
    python tools/validate_scoring.py --case 5   # 只跑第 5 组，调 prompt 时用
    python tools/validate_scoring.py --case 5 --raw   # 附带原始 JSON

这一步的目的不是"跑通"，是**用眼睛看分数合不合理**：
好的译法该拿高分，中式英语该在自然度上掉下来，语法错的该在语法上被抓住。
看到不合理的分数就改 score_prompt.py，重跑。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import scoring  # noqa: E402

# ---------------------------------------------------------------- 测试集
# (中文原文, [(译法说明, 英文译文), ...])
# 覆盖的坑：时态、主谓一致、介词、冠词、不规则动词、中式搭配、
# 近义词误用、比较句、used to / be used to 混淆、suggest 的用法。

CASES = [
    ("我今天很累。", [
        ("好的", "I'm really tired today."),
        ("中式", "I very tired today."),
        ("错介词", "I am very tired in today."),
    ]),
    ("他把书放在桌子上了。", [
        ("好的", "He put the book on the table."),
        ("时态错", "He puts the book on the table."),
        ("不规则动词错", "He putted the book on the table."),
    ]),
    ("我习惯早上六点起床。", [
        ("好的", "I'm used to getting up at six in the morning."),
        ("意思跑偏", "I used to get up at six in the morning."),
        ("可以但生硬", "I am accustomed to rise at six o'clock in the morning."),
    ]),
    ("这部电影我看过三遍了。", [
        ("好的", "I've seen this movie three times."),
        ("时态偏差", "I saw this movie three times."),
    ]),
    ("虽然下雨了，我们还是去了。", [
        ("好的", "Although it rained, we still went."),
        ("经典中式", "Although it rained, but we still went."),
        ("好的变体", "Even though it was raining, we went anyway."),
    ]),
    ("他建议我早点休息。", [
        ("好的", "He suggested that I get some rest earlier."),
        ("典型错误", "He suggested me to rest earlier."),
    ]),
    ("我昨天没收到你的邮件。", [
        ("好的", "I didn't get your email yesterday."),
        ("动词形式错", "I didn't received your email yesterday."),
    ]),
    ("请把空调关掉。", [
        ("好的", "Please turn off the air conditioner."),
        ("近义词误用", "Please close the air conditioner."),
    ]),
    ("这儿的天气比北京暖和。", [
        ("好的", "The weather here is warmer than in Beijing."),
        ("比较对象错", "The weather here is more warm than Beijing."),
    ]),
    ("我宁愿待在家里也不出去。", [
        ("好的", "I'd rather stay at home than go out."),
        ("好的变体", "I would rather stay home than go out."),
        ("搭配错", "I would rather stay at home instead of go out."),
    ]),
]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=int, help="只跑第 N 组（从 1 开始）")
    parser.add_argument("--effort", default=None,
                        choices=["low", "medium", "high", "xhigh", "max"],
                        help="思考深度。不传用 API 默认（high）")
    parser.add_argument("--raw", action="store_true", help="打印原始 JSON")
    args = parser.parse_args()

    if args.case and not 1 <= args.case <= len(CASES):
        print(f"错误：--case 取值范围 1-{len(CASES)}", file=sys.stderr)
        return 1

    try:
        client = scoring.require_client()
    except scoring.ScoringError as e:
        print(e, file=sys.stderr)
        return 1

    cases = [CASES[args.case - 1]] if args.case else CASES
    total = sum(len(v) for _, v in cases)
    done = 0
    usage = scoring.Usage(0, 0)

    for chinese, variants in cases:
        for label, english in variants:
            done += 1
            try:
                result, u = scoring.score(chinese, english, client=client,
                                          effort=args.effort)
            except scoring.ScoringError as e:
                print(f"\n[{done}/{total}] {chinese} / {english}\n  {e}", file=sys.stderr)
                continue

            usage = usage + u
            s = result.scores
            print(f"\n{'=' * 72}")
            print(f"[{done}/{total}] {chinese}")
            print(f"  译法 ({label}): {english}")
            print(f"  语义 {s.meaning:3d} | 语法 {s.grammar:3d} | "
                  f"自然度 {s.naturalness:3d} | 用词 {s.vocabulary:3d}"
                  f"   →  总分 {result.overall}")
            if result.issues:
                print("  问题:")
                for issue in result.issues:
                    print(f"    · 「{issue.span}」[{issue.type}] {issue.explain}")
            else:
                print("  问题: 无")
            print(f"  参考: {result.reference}")
            if result.also_acceptable:
                print(f"  也可: {' / '.join(result.also_acceptable)}")
            print(f"  点评: {result.comment}")
            if args.raw:
                print(f"  --- raw ---\n{result.model_dump_json(indent=2)}")

    print(f"\n{'=' * 72}")
    print(f"完成 {done} 次调用 | 输入 {usage.input_tokens} tokens, "
          f"输出 {usage.output_tokens} tokens | 约 ${usage.cost_usd:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
