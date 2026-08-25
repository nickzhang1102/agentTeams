"""
Leader Node Utils

节点间共享的纯工具函数（无服务依赖）。
"""
from datetime import datetime


def build_current_date_prompt() -> str:
    """构建当前日期注入文本（DRY：agent_report_synthesizer + summarize_nodes 共用）

    Returns:
        附加到 system prompt 的日期字符串，格式示例：
        "\\n\\n**当前日期**: 2026年06月25日\\n
        生成报告时，请使用当前日期（2026年06月25日）作为报告日期，不要使用过时的日期。"
    """
    current_date = datetime.now().strftime("%Y年%m月%d日")
    return (
        f"\n\n**当前日期**: {current_date}\n"
        f"生成报告时，请使用当前日期（{current_date}）作为报告日期，不要使用过时的日期。"
    )
