# Casen

Casual Sentence —— 中译英练习。

导入中文句子，自己翻成英文，AI 逐维度评分并给出参考答案和问题定位，
然后按记忆曲线安排复习。

## 现在有什么

`tools/` 下是一个命令行原型，用来把「导入 → 翻译 → 评分 → 复习」整个流程跑顺。
**界面还没做**，用哪个技术栈也还没定。

用法见 [tools/README.md](tools/README.md)。

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python tools/casen.py import tools/sentences.sample.txt
python tools/casen.py practice
```

## 注意

仓库根目录这套 Android + Compose 骨架（`build.gradle.kts`、`settings.gradle.kts`、
`gradlew`）**目前是跑不起来的**：缺少 `gradle/wrapper/`，`local.properties` 指向的还是
另一台机器的 SDK 路径。等确定要不要走原生 Android 这条路时再处理。

如果最终不做原生 Android，可以考虑删掉这些文件，或改用 Flutter ——
这台机器上 Flutter 3.44.1 是现成可用的。

## 设计要点

评分不是给一个笼统的分数，而是分四个维度（语义 / 语法 / 自然度 / 用词），
并且**指出问题出现在哪几个词上**（`span` 字段，界面上高亮显示）。

几条刻意的设计：

- **翻译没有唯一答案。** 评分会额外给出 `also_acceptable`，避免写出地道同义句反被扣分。
- **语义是门槛。** 总分是加权而非平均，语义低于 60 时封顶 —— 意思传错了，语言再漂亮也没完成任务。
- **只给分数没有价值。** 每条问题都要说清错在哪、为什么、正确写法是什么。
