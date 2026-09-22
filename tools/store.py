"""句子库和练习记录。SQLite + 标准库，没有额外依赖。

复习节奏用简化的 Leitner 盒子：每句一个 box（0-5），连着答得好就往后推，
答砸了就往回退。box 决定下次什么时候该复习。

box 0 是特殊值 —— 表示"还没练过或刚答砸"，当天就该再见到。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# box -> 间隔天数
INTERVALS = {0: 0, 1: 1, 2: 3, 3: 7, 4: 16, 5: 35}
MAX_BOX = 5

# 分数分档
PASS = 85      # 达到就往后推一个盒子
WEAK = 60      # 低于这个就往回退

SCHEMA = """
CREATE TABLE IF NOT EXISTS sentences (
    id         INTEGER PRIMARY KEY,
    chinese    TEXT NOT NULL UNIQUE,
    tag        TEXT NOT NULL DEFAULT '',
    box        INTEGER NOT NULL DEFAULT 0,
    due_at     TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id             INTEGER PRIMARY KEY,
    sentence_id    INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    english        TEXT NOT NULL,
    overall        INTEGER NOT NULL,
    meaning        INTEGER NOT NULL,
    grammar        INTEGER NOT NULL,
    naturalness    INTEGER NOT NULL,
    vocabulary     INTEGER NOT NULL,
    issues         TEXT NOT NULL,
    reference      TEXT NOT NULL,
    also_acceptable TEXT NOT NULL,
    comment        TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_sentence ON attempts(sentence_id);
CREATE INDEX IF NOT EXISTS idx_sentences_due ON sentences(due_at);
"""


@dataclass
class Sentence:
    id: int
    chinese: str
    tag: str
    box: int
    due_at: str


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------- 导入

def add_sentences(conn: sqlite3.Connection, items: list[tuple[str, str]]) -> tuple[int, int]:
    """items 是 (中文, 标签) 列表。返回 (新增数, 跳过数)。

    中文相同的视为同一句，跳过不重复导入 —— 重复导入同一个文件是安全的。
    """
    today = date.today().isoformat()
    added = skipped = 0
    for chinese, tag in items:
        cur = conn.execute(
            "INSERT OR IGNORE INTO sentences (chinese, tag, box, due_at, created_at) "
            "VALUES (?, ?, 0, ?, ?)",
            (chinese, tag, today, today),
        )
        if cur.rowcount:
            added += 1
        else:
            skipped += 1
    conn.commit()
    return added, skipped


# ---------------------------------------------------------------- 取题

def due_sentences(conn: sqlite3.Connection, tag: str | None = None,
                  limit: int | None = None,
                  include_future: bool = False) -> list[Sentence]:
    """取今天该练的句子。还没练过的（box 0）排在前面。

    include_future=True 时不管到期没到期全取出来（--all 用）。
    """
    sql = "SELECT id, chinese, tag, box, due_at FROM sentences WHERE 1=1"
    params: list = []
    if not include_future:
        sql += " AND due_at <= ?"
        params.append(date.today().isoformat())
    if tag:
        sql += " AND tag = ?"
        params.append(tag)
    sql += " ORDER BY box ASC, id ASC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return [Sentence(**dict(row)) for row in conn.execute(sql, params)]


def weak_sentences(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    """按最近一次成绩由低到高排，用来看看哪几句一直过不去。"""
    return list(conn.execute("""
        SELECT s.*, a.overall, a.grammar, a.created_at AS last_at
        FROM sentences s
        JOIN attempts a ON a.id = (
            SELECT id FROM attempts WHERE sentence_id = s.id
            ORDER BY id DESC LIMIT 1
        )
        ORDER BY a.overall ASC, a.id DESC
        LIMIT ?
    """, (limit,)))


def all_tags(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    return [(row["tag"], row["n"]) for row in conn.execute(
        "SELECT tag, COUNT(*) AS n FROM sentences GROUP BY tag ORDER BY tag"
    )]


# ---------------------------------------------------------------- 记录成绩

def record_attempt(conn: sqlite3.Connection, sentence: Sentence,
                   english: str, result) -> int:
    """存一次练习，并更新这句的复习盒子。返回新的 box。"""
    today = date.today()
    overall = result.overall

    if overall >= PASS:
        new_box = min(sentence.box + 1, MAX_BOX)
    elif overall >= WEAK:
        new_box = max(sentence.box, 1)   # 没过关，但不算砸，维持节奏
    else:
        new_box = max(0, sentence.box - 1)

    due = today + timedelta(days=INTERVALS[new_box])

    conn.execute(
        "INSERT INTO attempts (sentence_id, english, overall, meaning, grammar, "
        "naturalness, vocabulary, issues, reference, also_acceptable, comment, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            sentence.id, english, overall,
            result.scores.meaning, result.scores.grammar,
            result.scores.naturalness, result.scores.vocabulary,
            json.dumps([i.model_dump() for i in result.issues], ensure_ascii=False),
            result.reference,
            json.dumps(result.also_acceptable, ensure_ascii=False),
            result.comment,
            today.isoformat(),
        ),
    )
    conn.execute("UPDATE sentences SET box = ?, due_at = ? WHERE id = ?",
                 (new_box, due.isoformat(), sentence.id))
    conn.commit()
    return new_box


# ---------------------------------------------------------------- 统计

def stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    practiced = conn.execute(
        "SELECT COUNT(DISTINCT sentence_id) FROM attempts").fetchone()[0]
    attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]

    row = conn.execute("""
        SELECT AVG(overall) AS overall, AVG(meaning) AS meaning,
               AVG(grammar) AS grammar, AVG(naturalness) AS naturalness,
               AVG(vocabulary) AS vocabulary
        FROM (SELECT * FROM attempts ORDER BY id DESC LIMIT 100)
    """).fetchone()

    due = conn.execute("SELECT COUNT(*) FROM sentences WHERE due_at <= ?",
                       (date.today().isoformat(),)).fetchone()[0]

    return {
        "total": total,
        "practiced": practiced,
        "attempts": attempts,
        "due": due,
        "avg": {k: (row[k] or 0) for k in
                ("overall", "meaning", "grammar", "naturalness", "vocabulary")},
    }
