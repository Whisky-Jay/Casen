# Casen 命令行原型

中译英练习：导入中文句子 → 自己翻成英文 → AI 评分 → 按记忆曲线安排复习。

先把整个流程跑顺用的，界面以后再说。

## 装依赖

```bash
pip install anthropic
```

## 配 API key

评分走 Claude API，需要 key（不便宜但一天几十句花不了几毛钱）：

```bash
# bash / Git Bash
export ANTHROPIC_API_KEY=sk-ant-...

# PowerShell
$env:ANTHROPIC_API_KEY="sk-ant-..."
```

## 用

```bash
# 导入句子（先拿示例文件试试）
python tools/casen.py import tools/sentences.sample.txt

# 练今天该练的
python tools/casen.py practice

# 等不及了，全都拿出来练
python tools/casen.py practice --all --limit 5

# 只练某个标签
python tools/casen.py practice --tag 时态

# 看看整体情况
python tools/casen.py stats

# 哪几句一直过不去
python tools/casen.py weak
```

练习时：`回车` 或 `:s` 跳过，`:q` 退出。

## 句子文件格式

一行一句中文。空行和 `#` 开头的行忽略。`@标签` 单独占一行，给它后面的句子打标签：

```
@日常
我今天特别累，什么都不想干。
这周末你有什么打算吗？

@时态
我在这家公司工作了五年了。
```

同一句重复导入会被跳过，所以反复导入同一个文件是安全的。

## 复习节奏

每句一个「盒子」（0-5），盒子决定下次什么时候复习：

| 这次得分 | 盒子变化 | 下次 |
|---|---|---|
| ≥ 85 | +1（最高 5） | 1 / 3 / 7 / 16 / 35 天后 |
| 60-84 | 不变 | 维持原节奏 |
| < 60 | −1 | 往前挪，很快再见 |

新句子盒子是 0，当天就该练。

## 花费

`practice` 和 `validate_scoring.py` 跑完都会打印实际花费。想省钱可以调低思考深度：

```bash
python tools/casen.py practice --effort low
```

## 文件

| 文件 | 干什么的 |
|---|---|
| `casen.py` | 命令行入口 |
| `store.py` | 句子库和练习记录（SQLite，无额外依赖） |
| `scoring.py` | **唯一**调 Claude API 的地方 |
| `score_prompt.py` | 评分 prompt 本体，改评分效果改这里 |
| `validate_scoring.py` | 批量验证评分质量，调 prompt 时用 |
| `_smoke.py` | 离线冒烟测试，不碰 API，改完代码先跑这个 |

## 调 prompt 的流程

评分效果不满意时：

```bash
python tools/validate_scoring.py --case 5 --raw   # 先看单组
python tools/validate_scoring.py                  # 再全跑（30 次调用）
```

看三件事：好的译法是不是都上了 85、中式英语的自然度是不是明显低于语法分、
`span` 能不能在原文里精确定位到。不理想就改 `score_prompt.py` 重跑。

改完代码记得：

```bash
python tools/_smoke.py
```

## 还没做的

- 界面（Android / Flutter 都没定）
- 评分结果还没做缓存，同一句同一个译法重复提交会重复计费
- 句子库没有导出
