"""Versioned prompt metadata for the stage-three narrative adapter."""

PROFILE_PROMPT_VERSION = "stage3-profile-v1"


def build_profile_prompt(facts: dict) -> str:
    return (
        "根据给定的结构化评分事实生成辅助性人才画像叙述。"
        "不得修改分数、匹配度或状态；INCOMPLETE 必须表述为不可完全评价。"
        f"\n事实：{facts}"
    )
