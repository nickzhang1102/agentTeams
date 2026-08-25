"""
DAGPlanner 测试

测试 priority 驱动的执行计划生成器
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from leader.dag_planner import DAGPlanner, DAGExecutionPlan


class TestDAGPlanner:
    """DAGPlanner 核心功能测试"""

    def setup_method(self):
        """每个测试前初始化"""
        self.db_session = Mock()
        self.agent_reader = Mock()

        self.planner = DAGPlanner(self.db_session, self.agent_reader)

    def test_build_nodes_with_priority_from_metadata(self):
        """测试从元数据获取 priority"""
        # Mock agent_reader 返回 priority=40
        self.agent_reader.get_agent_metadata.return_value = {'priority': 40}

        selected_agents = [
            {"agent_id": "检验科专家", "agent_name": "检验科专家", "role_description": "检验分析"}
        ]

        nodes = self.planner._build_nodes_with_priority(selected_agents)

        assert len(nodes) == 1
        assert nodes[0]["priority"] == 40
        assert nodes[0]["priority_source"] == "default"

    def test_build_nodes_infer_priority_for_critic(self):
        """测试推断审核类 Agent priority"""
        # Mock agent_reader 返回无 priority
        self.agent_reader.get_agent_metadata.return_value = {}

        selected_agents = [
            {"agent_id": "critic-munger", "agent_name": "逆向思考顾问", "role_description": "审核"}
        ]

        nodes = self.planner._build_nodes_with_priority(selected_agents)

        assert nodes[0]["priority"] == 90  # 审核类默认 90

    def test_build_nodes_infer_priority_for_lab(self):
        """测试推断前置类 Agent priority"""
        # Mock agent_reader 返回无 priority
        self.agent_reader.get_agent_metadata.return_value = {}

        selected_agents = [
            {"agent_id": "检验科专家", "agent_name": "检验科专家", "role_description": "检验分析"}
        ]

        nodes = self.planner._build_nodes_with_priority(selected_agents)

        assert nodes[0]["priority"] == 40  # 前置类默认 40

    def test_build_nodes_default_priority(self):
        """测试默认 priority"""
        # Mock agent_reader 返回无 priority
        self.agent_reader.get_agent_metadata.return_value = {}

        selected_agents = [
            {"agent_id": "肿瘤内科专家", "agent_name": "肿瘤内科专家", "role_description": "肿瘤诊断"}
        ]

        nodes = self.planner._build_nodes_with_priority(selected_agents)

        assert nodes[0]["priority"] == 50  # 默认并行

    def test_load_matching_rules_filters_by_scene(self):
        """测试规则按场景过滤（SQL 级别过滤，DB 返回已匹配的规则）"""
        # 模拟 DB 返回已过滤的规则（SQL WHERE 已完成场景过滤）
        rule1 = Mock()
        rule1.id = 1
        rule1.trigger_scene = "technology"
        rule1.trigger_risk_level = None
        rule1.trigger_category = None
        rule1.is_active = True

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [rule1]  # DB 只返回匹配的规则
        self.db_session.query.return_value = mock_query

        matched = self.planner._load_matching_rules("technology", "medium", None)

        assert len(matched) == 1
        assert matched[0].id == 1

    def test_load_matching_rules_sql_includes_empty_string_wildcard(self):
        """测试 SQL WHERE 包含空字符串通配分支（与 matches() 空串通配语义一致）

        matches() 把 trigger_xxx='' 视为通配（匹配任意），SQL 下推后也需
        同等对待：is_(None) / == '*' / == '' / == param 四路 OR。
        """
        from sqlalchemy import or_

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        self.db_session.query.return_value = mock_query

        self.planner._load_matching_rules("technology", "medium", "")

        # filter() 第一个调用是 is_active == True，后续三个是 OR 条件
        filter_calls = list(mock_query.filter.call_args_list)
        assert len(filter_calls) == 1, "应只有一次 filter() 调用（多条件 AND 合并）"
        args = filter_calls[0][0]  # positional args

        # 提取三个 or_() 条件（跳过第一个 is_active == True）
        or_conditions = [a for a in args if isinstance(a, type(or_()))]

        # 每个 OR 条件应含 4 个分支：is_(None) / == '*' / == '' / == param
        for cond, field_name in zip(or_conditions, ['trigger_scene', 'trigger_risk_level', 'trigger_category']):
            clauses = list(cond.clauses)
            assert len(clauses) == 4, (
                f"{field_name} OR 条件应含 4 分支 (is_(None), =='*', =='', ==param)，"
                f"实际 {len(clauses)} 个"
            )

    def test_apply_priority_rules_overrides_default(self):
        """测试规则覆盖默认 priority"""
        nodes = [
            {"id": "agent_1", "agent_id": "critic-munger", "priority": 90, "priority_source": "default"}
        ]

        rule = Mock()
        rule.id = 1
        rule.agent_id = "critic-munger"
        rule.priority = 95
        rule.rule_priority = 10

        updated_nodes = self.planner._apply_priority_rules(nodes, [rule])

        assert updated_nodes[0]["priority"] == 95
        assert updated_nodes[0]["priority_source"] == "rule:1"

    def test_apply_priority_rules_rule_priority_order(self):
        """测试 rule_priority 大者优先"""
        nodes = [
            {"id": "agent_1", "agent_id": "test-agent", "priority": 50, "priority_source": "default"}
        ]

        # rule_priority 较低的规则（先应用）
        rule1 = Mock()
        rule1.id = 1
        rule1.agent_id = "test-agent"
        rule1.priority = 60
        rule1.rule_priority = 5

        # rule_priority 较高的规则（后应用，覆盖）
        rule2 = Mock()
        rule2.id = 2
        rule2.agent_id = "test-agent"
        rule2.priority = 40
        rule2.rule_priority = 10

        # 按 rule_priority 升序传入（模拟 _load_matching_rules 返回顺序）
        updated_nodes = self.planner._apply_priority_rules(nodes, [rule1, rule2])

        # rule_priority=10 的规则最终覆盖（大者优先）
        assert updated_nodes[0]["priority"] == 40
        assert updated_nodes[0]["priority_source"] == "rule:2"

    def test_build_execution_batches_sorts_by_priority(self):
        """测试批次按 priority 升序分组"""
        nodes = [
            {"agent_id": "agent_3", "priority": 90},
            {"agent_id": "agent_1", "priority": 40},
            {"agent_id": "agent_2", "priority": 50},
        ]

        batches = self.planner._build_execution_batches(nodes)

        assert len(batches) == 3
        assert batches[0]["priority"] == 40
        assert batches[1]["priority"] == 50
        assert batches[2]["priority"] == 90

    def test_build_execution_batches_groups_same_priority(self):
        """测试相同 priority 并行分组"""
        nodes = [
            {"agent_id": "agent_1", "priority": 50},
            {"agent_id": "agent_2", "priority": 50},
            {"agent_id": "agent_3", "priority": 50},
        ]

        batches = self.planner._build_execution_batches(nodes)

        assert len(batches) == 1
        assert batches[0]["priority"] == 50
        assert len(batches[0]["agents"]) == 3

    def test_get_current_batch_returns_first_unfinished(self):
        """测试获取当前未完成批次"""
        plan = DAGExecutionPlan(
            nodes=[
                {"id": "agent_1", "priority": 40},
                {"id": "agent_2", "priority": 50},
                {"id": "agent_3", "priority": 90},
            ],
            execution_batches=[
                {"priority": 40, "agents": ["agent_1"]},
                {"priority": 50, "agents": ["agent_2"]},
                {"priority": 90, "agents": ["agent_3"]},
            ],
            matched_rules=[]
        )

        # 初始：返回第一批
        batch = self.planner.get_current_batch(plan, [])
        assert batch == ["agent_1"]

        # 完成 agent_1：返回第二批
        batch = self.planner.get_current_batch(plan, ["agent_1"])
        assert batch == ["agent_2"]

        # 完成 agent_1, agent_2：返回第三批
        batch = self.planner.get_current_batch(plan, ["agent_1", "agent_2"])
        assert batch == ["agent_3"]

        # 全部完成：返回空
        batch = self.planner.get_current_batch(plan, ["agent_1", "agent_2", "agent_3"])
        assert batch == []

    def test_plan_from_requirement_integration(self):
        """测试完整流程：生成执行计划"""
        # Mock agent_reader
        self.agent_reader.get_agent_metadata.return_value = {'priority': 50}

        # Mock 规则查询（使用普通 Mock）
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        self.db_session.query.return_value = mock_query

        selected_agents = [
            {"agent_id": "agent_1", "agent_name": "Agent 1", "role_description": "Role 1"},
            {"agent_id": "agent_2", "agent_name": "Agent 2", "role_description": "Role 2"},
        ]

        plan = self.planner.plan_from_requirement(
            selected_agents=selected_agents,
            risk_level="medium",
            scene="technology",
            category=None
        )

        assert len(plan["nodes"]) == 2
        assert len(plan["execution_batches"]) >= 1
        assert plan["matched_rules"] == []


class TestAgentPriorityRuleMatches:
    """测试 AgentPriorityRule.matches() 方法"""

    def test_matches_null_trigger_matches_all(self):
        """测试 null 触发条件匹配所有"""
        from models import AgentPriorityRule

        rule = AgentPriorityRule(
            trigger_scene=None,
            trigger_risk_level=None,
            trigger_category=None,
            is_active=True
        )

        # 匹配任意场景
        assert rule.matches("technology", "high", "investment") is True
        assert rule.matches("medical", "low", "肿瘤") is True

    def test_matches_wildcard_matches_all(self):
        """测试 '*' 通配符匹配所有"""
        from models import AgentPriorityRule

        rule = AgentPriorityRule(
            trigger_scene='*',
            trigger_risk_level='*',
            trigger_category='*',
            is_active=True
        )

        assert rule.matches("technology", "high", "investment") is True

    def test_matches_specific_value(self):
        """测试具体值匹配"""
        from models import AgentPriorityRule

        rule = AgentPriorityRule(
            trigger_scene="technology",
            trigger_risk_level="high",
            trigger_category=None,
            is_active=True
        )

        # 匹配
        assert rule.matches("technology", "high", "anything") is True

        # 不匹配
        assert rule.matches("medical", "high", "anything") is False
        assert rule.matches("technology", "low", "anything") is False

    def test_matches_inactive_rule_not_matches(self):
        """测试禁用规则不匹配"""
        from models import AgentPriorityRule

        rule = AgentPriorityRule(
            trigger_scene=None,
            trigger_risk_level=None,
            trigger_category=None,
            is_active=False
        )

        assert rule.matches("technology", "high", "investment") is False


class TestDAGExecutionPlanTypedDict:
    """测试 DAGExecutionPlan 类型定义"""

    def test_plan_structure(self):
        """测试执行计划结构"""
        plan = DAGExecutionPlan(
            nodes=[
                {"id": "agent_1", "agent_id": "test", "priority": 50, "priority_source": "default"}
            ],
            execution_batches=[
                {"priority": 50, "agents": ["agent_1"]}
            ],
            matched_rules=[1, 2]
        )

        assert plan["nodes"][0]["priority"] == 50
        assert plan["execution_batches"][0]["priority"] == 50
        assert plan["matched_rules"] == [1, 2]


class TestExecutionOrderDescription:
    """测试执行顺序描述生成"""

    def test_single_batch_description(self):
        """测试单批次描述"""
        plan = DAGExecutionPlan(
            nodes=[],
            execution_batches=[{"priority": 50, "agents": ["agent_1"]}],
            matched_rules=[]
        )

        desc = self.planner.get_execution_order_description(plan)
        assert "批次 1" in desc
        assert "priority=50" in desc

    def test_parallel_batch_description(self):
        """测试并行批次描述"""
        plan = DAGExecutionPlan(
            nodes=[],
            execution_batches=[{"priority": 50, "agents": ["agent_1", "agent_2"]}],
            matched_rules=[]
        )

        desc = self.planner.get_execution_order_description(plan)
        assert "并行" in desc

    def setup_method(self):
        """初始化 planner"""
        self.planner = DAGPlanner(Mock(), Mock())
