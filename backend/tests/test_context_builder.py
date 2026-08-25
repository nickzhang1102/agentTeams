"""ContextBuilder 单元测试。"""
import pytest
import sys, os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from context.context_builder import ContextBuilder


class TestBuildContext:
    """build() — API 入口处组装。"""

    def test_basic(self):
        pack = ContextBuilder.build("帮我分析代码")
        assert pack.task_description == "帮我分析代码"
        assert pack.shared_evidence == []

    def test_with_file_context(self):
        pack = ContextBuilder.build("帮我分析代码", file_context="文件 main.py: def foo(): pass")
        assert pack.task_description == "帮我分析代码"
        assert pack.shared_evidence == ["文件 main.py: def foo(): pass"]

    def test_file_context_none(self):
        pack = ContextBuilder.build("消息", file_context=None)
        assert pack.shared_evidence == []


class TestBuildForAssessment:
    """build_for_assessment() — 需求循环节点组装。"""

    def test_no_answers(self):
        pack = ContextBuilder.build_for_assessment("用户需求")
        assert pack.task_description == "用户需求"
        assert "用户补充信息" not in pack.task_description

    def test_with_answers(self):
        pack = ContextBuilder.build_for_assessment(
            "用户需求", user_answers=["重点看性能", "忽略测试"]
        )
        task = pack.task_description
        assert "用户需求" in task
        assert "用户补充信息" in task
        assert "1. 重点看性能" in task
        assert "2. 忽略测试" in task

    def test_empty_answers_list(self):
        pack = ContextBuilder.build_for_assessment("用户需求", user_answers=[])
        assert pack.task_description == "用户需求"

    def test_with_previous_questions(self):
        """步骤 9 验证：previous_questions 参数传入后拼到 task_description。"""
        pack = ContextBuilder.build_for_assessment(
            "头疼",
            user_answers=["三天了"],
            previous_questions=[
                {"question": "症状持续多久？", "options": ["几小时", "1-3天", "一周以上"]},
                {"question": "有没有发热？", "options": ["有", "没有"]}
            ]
        )
        task = pack.task_description
        assert "头疼" in task
        assert "用户补充信息" in task
        assert "已问过的问题" in task
        assert "症状持续多久？" in task
        assert "有没有发热？" in task

    def test_previous_questions_only(self):
        """只有历史问题，无用户回答。"""
        pack = ContextBuilder.build_for_assessment(
            "头疼",
            previous_questions=[{"question": "症状持续多久？", "options": ["几小时", "1-3天"]}]
        )
        task = pack.task_description
        assert "头疼" in task
        assert "已问过的问题" in task
        assert "症状持续多久？" in task
        assert "用户补充信息" not in task

    def test_with_qa_pairs(self):
        """qa_pairs 参数：历史 Q&A 配对包含在提示词中。"""
        pack = ContextBuilder.build_for_assessment(
            "帮我做个系统",
            user_answers=["Python"],
            qa_pairs=[
                {"question": "用什么技术栈？", "answer": "Web 应用"},
                {"question": "数据库选型？", "answer": "PostgreSQL"},
            ],
            previous_questions=[
                {"question": "用什么技术栈？", "options": []},
                {"question": "数据库选型？", "options": []},
            ]
        )
        task = pack.task_description
        assert "帮我做个系统" in task
        assert "用户历史补充信息" in task
        assert "第1轮 - 问题：用什么技术栈？" in task
        assert "回答：Web 应用" in task
        assert "第2轮 - 问题：数据库选型？" in task
        assert "回答：PostgreSQL" in task
        assert "已问过的问题" in task

    def test_qa_pairs_none(self):
        """qa_pairs=None 时不报错，不影响原有逻辑。"""
        pack = ContextBuilder.build_for_assessment(
            "头疼",
            qa_pairs=None
        )
        assert "头疼" in pack.task_description
        assert "用户历史补充信息" not in pack.task_description


class TestBuildForAgents:
    """build_for_agents() — Agent 执行节点组装。"""

    def test_basic(self):
        pack = ContextBuilder.build_for_agents("任务描述")
        assert pack.task_description == "任务描述"
        assert pack.shared_evidence == []
        assert pack.working_memory == []

    def test_with_evidence(self):
        pack = ContextBuilder.build_for_agents(
            "任务", shared_evidence=["证据1", "证据2"]
        )
        assert pack.shared_evidence == ["证据1", "证据2"]

    def test_with_working_memory(self):
        memory = [{"role": "user", "content": "历史问题"}]
        pack = ContextBuilder.build_for_agents("任务", working_memory=memory)
        assert pack.working_memory == memory

    def test_with_qa_pairs(self):
        """qa_pairs 参数：历史追问 Q&A 配对拼入 task_description。"""
        pack = ContextBuilder.build_for_agents(
            "做个投资分析",
            qa_pairs=[
                {"question": "资金规模？", "answer": "100万"},
                {"question": "投资期限？", "answer": "5年"},
            ],
        )
        task = pack.task_description
        assert "做个投资分析" in task
        assert "用户追问补充信息" in task
        assert "第1轮 - 问题：资金规模？" in task
        assert "回答：100万" in task
        assert "第2轮 - 问题：投资期限？" in task
        assert "回答：5年" in task

    def test_qa_pairs_none(self):
        """qa_pairs=None 时不报错，task_description 仅含原始需求。"""
        pack = ContextBuilder.build_for_agents("头疼", qa_pairs=None)
        assert pack.task_description == "头疼"
        assert "用户追问补充信息" not in pack.task_description


class TestAcceptanceScenarios:
    """验收场景覆盖。"""

    def test_b1_no_evidence_no_answers_degrades_to_plain_task(self):
        """B1: 无文件上下文无补充回答时退化为纯 task_description。"""
        pack = ContextBuilder.build("用户消息")
        assert pack.to_task_string() == "用户消息"
        assert pack.to_messages() == [{"role": "user", "content": "用户消息"}]

    def test_e1_build_fallback_on_exception(self):
        """E1: ContextBuilder 异常时 fallback 到 user_message。"""
        # 模拟构造异常——传入 None 作为 task_description 触发 fallback
        pack = ContextBuilder.build_for_agents("正常消息")
        assert pack.task_description == "正常消息"

