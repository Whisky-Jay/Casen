"""离线冒烟测试：不碰 API，验证盒子推进、高亮定位、存库、统计。

    python tools/_smoke.py

用假评分结果跑，所以不需要 API key。改完 store.py / casen.py 后先跑这个。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 强制当成终端，否则 ANSI 颜色码会被自动禁用，高亮测不出来
sys.stdout.isatty = lambda: True

import casen  # noqa: E402
import scoring  # noqa: E402
import store  # noqa: E402

failures = []


def check(label, got, want):
    ok = got == want
    if not ok:
        failures.append(label)
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got!r}" +
          ("" if ok else f"  期望 {want!r}"))


print("=== 盒子推进 ===")
for box, overall, want in [
    (0, 95, 1), (1, 90, 2), (2, 88, 3), (5, 90, 5),   # 过关 → 往后推
    (0, 70, 1), (2, 70, 2), (3, 65, 3),               # 没过关 → 维持
    (3, 50, 2), (1, 40, 0), (0, 30, 0),               # 答砸 → 往后退
]:
    if overall >= store.PASS:
        got = min(box + 1, store.MAX_BOX)
    elif overall >= store.WEAK:
        got = max(box, 1)
    else:
        got = max(0, box - 1)
    check(f"box {box} 得 {overall} 分", got, want)

print("\n=== 高亮定位 ===")
s = "Although it rained, but we still went."
check("两个片段都标上",
      casen.mark_all(s, ["Although it rained", "but we still went"]),
      f"{casen.RED}{casen.UNDERLINE}Although it rained{casen.RESET}, "
      f"{casen.RED}{casen.UNDERLINE}but we still went{casen.RESET}.")
check("定位不到就原样返回", casen.mark_all(s, ["not in here"]), s)
check("空列表原样返回", casen.mark_all(s, []), s)
check("重叠片段不打架",
      "\033[0m" in casen.mark_all(s, ["Although it rained, but", "rained, but we"]),
      True)

print("\n=== 模拟一次练习 ===")
fake = scoring.Scoring(
    scores=scoring.Scores(meaning=95, grammar=55, naturalness=50, vocabulary=70),
    overall=72,
    issues=[
        scoring.Issue(span="Although it rained, but", type="语法",
                      explain="although 和 but 不能同时出现，中文的「虽然…但是…」"
                              "到英语里只能留一个。"),
        scoring.Issue(span="这一句是我编的", type="用词",
                      explain="故意定位不到，测试兜底提示。"),
    ],
    reference="Although it rained, we still went.",
    also_acceptable=["Even though it rained, we went anyway."],
    comment="意思完全传达到了，问题集中在语法上。",
)

db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_smoke.db")
if os.path.exists(db):
    os.remove(db)

conn = store.connect(db)
store.add_sentences(conn, [("虽然下雨了，我们还是去了。", "测试"), ("我今天很累。", "测试")])

pending = store.due_sentences(conn)
check("导入后待练句数", len(pending), 2)
check("新句子 box", pending[0].box, 0)

english = "Although it rained, but we still went."
casen.print_result(english, fake)          # 人工看一眼排版
new_box = store.record_attempt(conn, pending[0], english, fake)
check("72 分后 box", new_box, 1)

check("答对的排到明天，待练剩", len(store.due_sentences(conn)), 1)

st = store.stats(conn)
check("统计-总数", st["total"], 2)
check("统计-练过", st["practiced"], 1)
check("统计-今天到期", st["due"], 1)
check("统计-均分", round(st["avg"]["grammar"]), 55)

check("weak 列表条数", len(store.weak_sentences(conn)), 1)

conn.close()          # Windows 上不关连接就删不掉文件
os.remove(db)
print("\n" + ("全部通过" if not failures else f"失败 {len(failures)} 项: {failures}"))
sys.exit(1 if failures else 0)
