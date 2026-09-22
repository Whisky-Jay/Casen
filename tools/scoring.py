"""评分：输出结构 + 调用 Claude API。

整个项目里**唯一**调 API 的地方。CLI、以后的 Android/Flutter 端都走这里，
换 UI 不用碰评分逻辑。
"""

from __future__ import annotations

import os
import sys
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_prompt import SYSTEM_PROMPT, build_user_message  # noqa: E402

MODEL = "claude-opus-5"
# claude-opus-5 定价（美元 / 1M tokens）
PRICE_IN = 5.00
PRICE_OUT = 25.00


class Issue(BaseModel):
    span: str = Field(
        description="用户译文里有问题的片段，必须逐字摘抄自用户译文，"
                    "不要改写或补全，要能直接用字符串查找定位"
    )
    type: Literal["语义", "语法", "自然度", "用词"] = Field(
        description="这个问题属于哪个维度"
    )
    explain: str = Field(description="中文解释：错在哪、为什么错、正确写法是什么")


class Scores(BaseModel):
    meaning: int = Field(ge=0, le=100, description="语义：中文原意传达得是否完整准确")
    grammar: int = Field(ge=0, le=100, description="语法：时态、主谓一致、冠词、单复数、介词、语序")
    naturalness: int = Field(ge=0, le=100, description="自然度：英语母语者会不会这么说")
    vocabulary: int = Field(ge=0, le=100, description="用词：选词是否准确、恰当、符合语境")


class Scoring(BaseModel):
    scores: Scores
    overall: int = Field(ge=0, le=100, description="总分，按加权公式计算，语义是门槛")
    issues: list[Issue] = Field(description="具体问题列表。没有问题就给空列表，不要硬凑")
    reference: str = Field(description="你给出的参考译文")
    also_acceptable: list[str] = Field(
        description="其他同样可接受的译法，0-3 条。只放真正没问题的，宁可留空"
    )
    comment: str = Field(description="中文点评，2-3 句：先指出最值得改进的一点，再给一句真诚的评价")


class Usage(NamedTuple):
    input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float:
        return (self.input_tokens * PRICE_IN + self.output_tokens * PRICE_OUT) / 1e6

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens,
                     self.output_tokens + other.output_tokens)


class ScoringError(RuntimeError):
    """评分没能完成。message 是可以直接展示给用户的中文。"""


def require_client():
    """建 API 客户端，凭据缺失时给一句人话。"""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ScoringError(
            "没有找到 ANTHROPIC_API_KEY。\n"
            "  bash:       export ANTHROPIC_API_KEY=sk-ant-...\n"
            "  PowerShell: $env:ANTHROPIC_API_KEY=\"sk-ant-...\""
        )
    import anthropic
    return anthropic.Anthropic()


def score(chinese: str, english: str, client=None,
          effort: str | None = None) -> tuple[Scoring, Usage]:
    """给一句中译英打分。失败时抛 ScoringError。"""
    import anthropic

    if client is None:
        client = require_client()

    kwargs = {}
    if effort:
        kwargs["output_config"] = {"effort": effort}

    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": build_user_message(chinese, english),
            }],
            output_format=Scoring,
            **kwargs,
        )
    except anthropic.APIStatusError as e:
        raise ScoringError(f"API 返回 {e.status_code}：{e.message}") from e
    except anthropic.APIConnectionError as e:
        raise ScoringError(f"连不上 API（{e}）。检查网络或代理设置。") from e

    if response.stop_reason == "refusal":
        raise ScoringError("这句被模型安全策略拒绝了，换一句试试。")

    usage = Usage(response.usage.input_tokens, response.usage.output_tokens)
    return response.parsed_output, usage
