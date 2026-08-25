"""上下文构建器，组装 ContextPack 替代 enhanced_message 拼接。"""
import logging
from typing import Optional

from .context_pack import ContextPack

logger = logging.getLogger(__name__)


class ContextBuilder:
    """组装 ContextPack 的工厂方法集合。

    每个 build 方法对应一处现有 enhanced_message 拼接点，
    异常时 fallback 到原始 user_message。
    """

    @staticmethod
    def build(
        user_message: str,
        file_context: Optional[str] = None,
    ) -> ContextPack:
        """API 入口处组装，替代 leader_api.py 的 file_context 拼接。

        Args:
            user_message: 用户原始消息。
            file_context: 文件上下文字符串（可空）。
        """
        try:
            evidence = [file_context] if file_context else []
            return ContextPack(
                task_description=user_message,
                shared_evidence=evidence,
            )
        except Exception:
            logger.warning("ContextBuilder.build failed, falling back to raw message", exc_info=True)
            return ContextPack(task_description=user_message)

    @staticmethod
    def build_for_assessment(
        user_message: str,
        user_answers: Optional[list[str]] = None,
        previous_questions: Optional[list[dict]] = None,
        qa_pairs: Optional[list[dict]] = None,
    ) -> ContextPack:
        """需求循环节点组装，替代 workflow_nodes.py 的用户回答拼接。

        评估提示词包含三部分信息：
        1. 用户原始需求（user_message）
        2. 历史 Q&A 配对（qa_pairs）—— 前几轮追问的问题和用户答案
        3. 已问问题列表（previous_questions）—— 供 LLM 去重

        Args:
            user_message: 用户原始消息。
            user_answers: 当轮用户补充回答列表（可空）。
            previous_questions: 之前已问过的问题列表（可空），格式 [{"question": "...", "options": [...]}]。
            qa_pairs: 历史 Q&A 配对（可空），格式 [{"question": "...", "answer": "..."}, ...]。
        """
        try:
            task = user_message

            # 拼接历史 Q&A（累积所有轮次，供评估器看到完整上下文）
            if qa_pairs:
                task += "\n\n**【用户历史补充信息】**\n"
                task += "以下是用户在之前追问轮次中提供的信息：\n"
                for i, qa in enumerate(qa_pairs, 1):
                    task += f"  第{i}轮 - 问题：{qa.get('question', '')}\n"
                    task += f"         回答：{qa.get('answer', '')}\n"

            # 拼接当轮用户补充回答（尚未进入 qa_pairs）
            if user_answers:
                task += "\n\n用户补充信息（本轮）：\n"
                for i, answer in enumerate(user_answers, 1):
                    task += f"{i}. {answer}\n"

            # 拼接历史问题（供 LLM 去重）- 使用醒目格式
            if previous_questions:
                task += "\n\n**【已问过的问题 - 禁止重复】**\n"
                task += "以下问题已经问过用户，请不要再问类似或相同的问题：\n"
                for i, q in enumerate(previous_questions, 1):
                    task += f"  {i}. {q.get('question', '')}\n"
                task += "\n请针对其他缺失维度提出**新的**问题。\n"

            return ContextPack(task_description=task)
        except Exception:
            logger.warning("ContextBuilder.build_for_assessment failed, falling back", exc_info=True)
            return ContextPack(task_description=user_message)

    @staticmethod
    def build_for_agents(
        user_message: str,
        shared_evidence: Optional[list[str]] = None,
        working_memory: Optional[list[dict]] = None,
        user_memory: Optional[list[str]] = None,
        qa_pairs: Optional[list[dict]] = None,
    ) -> ContextPack:
        """Agent 执行节点组装，替代 task=user_message 直接透传。

        提示词包含：用户原始需求 + 历史 Q&A 配对（追问中用户提供的补充信息），
        使 Agent 执行时具备完整需求上下文。

        Args:
            user_message: 用户原始需求消息。
            shared_evidence: 共享证据列表（文件内容、搜索结果等）。
            working_memory: 对话历史摘要或前序 Agent 结果。
            user_memory: 用户长期记忆列表（来自 MemoryService）。
            qa_pairs: 历史 Q&A 配对（可空），格式 [{"question": "...", "answer": "..."}, ...]。
        """
        try:
            task = user_message
            # 拼接历史 Q&A（需求追问中用户提供的完整补充信息）
            if qa_pairs:
                task += "\n\n**【用户追问补充信息】**\n"
                task += "以下是用户在需求追问中提供的信息：\n"
                for i, qa in enumerate(qa_pairs, 1):
                    task += f"  第{i}轮 - 问题：{qa.get('question', '')}\n"
                    task += f"         回答：{qa.get('answer', '')}\n"
            return ContextPack(
                task_description=task,
                shared_evidence=shared_evidence or [],
                working_memory=working_memory or [],
                user_memory=user_memory or [],
            )
        except Exception:
            logger.warning("ContextBuilder.build_for_agents failed, falling back", exc_info=True)
            return ContextPack(task_description=user_message)
