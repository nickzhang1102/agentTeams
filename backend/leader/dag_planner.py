"""
DAG 执行计划生成器

从 Agent 元数据读取默认 priority，从数据库读取规则覆盖 priority，
按 priority 升序排序生成执行批次（相同 priority 并行）。
"""
import logging
from typing import TypedDict, List, Dict, Optional, Any

logger = logging.getLogger(__name__)


# ==================== TypedDict 定义 ====================

class DAGExecutionPlan(TypedDict):
    """Agent DAG 执行计划

    执行顺序由 priority 决定：
    - 按 priority 升序排序（小值先执行）
    - 相同 priority 的 Agent 并行执行
    """
    # 节点列表（含 priority）
    nodes: List[Dict]

    # 执行批次（按 priority 分组）
    execution_batches: List[Dict]

    # 匹配的规则 ID 列表（用于追踪）
    matched_rules: List[int]


class DAGNode(TypedDict, total=False):
    """DAG 节点"""
    id: str              # 节点 ID（agent_1, agent_2...）
    agent_id: str        # Agent ID
    agent_name: str      # Agent 名称
    role_description: str  # 角色描述
    priority: int        # 执行优先级（小值先执行）
    priority_source: str # "default" | "rule:{rule_id}"


class ExecutionBatch(TypedDict):
    """执行批次"""
    priority: int        # 该批次的 priority 值
    agents: List[str]    # 该批次的节点 ID 列表（并行执行）


# ==================== DAGPlanner 类 ====================

class DAGPlanner:
    """DAG 执行计划生成器（priority 驱动）

    从 Agent 元数据读取默认 priority，从数据库读取规则覆盖 priority，
    按 priority 升序排序生成执行批次（相同 priority 并行）。
    """

    def __init__(self, db_session: Any, agent_reader: Any):
        """
        初始化 DAGPlanner

        Args:
            db_session: 数据库会话
            agent_reader: Agent 内容读取器（AgentContentReader）
        """
        self.db = db_session
        self.agent_reader = agent_reader

    def plan_from_requirement(
        self,
        selected_agents: List[Dict],
        risk_level: str,
        scene: str,
        category: Optional[str] = None
    ) -> DAGExecutionPlan:
        """
        根据需求、Agent 列表、风险等级生成 DAG 执行计划

        Args:
            selected_agents: TeamFormer 返回的 Agent 列表
            risk_level: 风险等级 (low/medium/high)
            scene: 场景类型 (technology/medical/investment/...)
            category: 分类（如：肿瘤、心血管，可选）

        Returns:
            DAGExecutionPlan: 包含节点、执行批次的执行图
        """
        # 1. 构建节点（获取默认 priority）
        nodes = self._build_nodes_with_priority(selected_agents)

        # 2. 从数据库加载匹配规则，覆盖 priority
        matched_rules = self._load_matching_rules(scene, risk_level, category)
        nodes = self._apply_priority_rules(nodes, matched_rules)

        # 3. 按 priority 分组生成执行批次
        execution_batches = self._build_execution_batches(nodes)

        return DAGExecutionPlan(
            nodes=nodes,
            execution_batches=execution_batches,
            matched_rules=[r.id for r in matched_rules]
        )

    def _build_nodes_with_priority(self, selected_agents: List[Dict]) -> List[Dict]:
        """构建节点列表，获取每个 Agent 的默认 priority

        Args:
            selected_agents: TeamFormer 返回的 Agent 列表

        Returns:
            节点列表（含 priority）
        """
        nodes = []
        for i, agent in enumerate(selected_agents, 1):
            agent_id = agent.get("agent_id", "")

            # 从 Agent 元数据获取默认 priority
            default_priority = self._get_agent_default_priority(agent_id)

            nodes.append({
                "id": f"agent_{i}",
                "agent_id": agent_id,
                "agent_name": agent.get("agent_name", ""),
                "role_description": agent.get("role_description", ""),
                "priority": default_priority,
                "priority_source": "default"
            })
        return nodes

    def _get_agent_default_priority(self, agent_id: str) -> int:
        """从 Agent 元数据获取默认 priority，未配置则推断

        优先级规划：
        - 审核类（critic-munger）: 90
        - 前置类（检验/放射/病理）: 40
        - 其他诊断类: 50

        Args:
            agent_id: Agent ID

        Returns:
            默认 priority 值
        """
        # 尝试从元数据解析
        agent_meta = self.agent_reader.get_agent_metadata(agent_id)
        if agent_meta and 'priority' in agent_meta:
            return int(agent_meta['priority'])

        # 根据 Agent 类型推断默认值
        if 'critic' in agent_id.lower() or '审核' in agent_id or 'reviewer' in agent_id.lower():
            return 90
        if '检验' in agent_id or '放射' in agent_id or '病理' in agent_id:
            return 40

        return 50  # 默认

    def _load_matching_rules(
        self,
        scene: str,
        risk_level: str,
        category: Optional[str]
    ) -> List[Any]:
        """从数据库加载匹配的规则（按 rule_priority 升序排序）

        过滤逻辑下推到 SQL WHERE，避免全量加载后 Python 逐条匹配。

        Args:
            scene: 场景类型
            risk_level: 风险等级
            category: 分类

        Returns:
            匹配的 AgentPriorityRule 列表（按 rule_priority 升序）
        """
        from models import AgentPriorityRule
        from sqlalchemy import or_

        cat = category or ''
        rules = self.db.query(AgentPriorityRule).filter(
            AgentPriorityRule.is_active == True,
            # scene 匹配：NULL 或 '*' 通配，或精确匹配
            or_(AgentPriorityRule.trigger_scene.is_(None),
                AgentPriorityRule.trigger_scene == '*',
                AgentPriorityRule.trigger_scene == '',
                AgentPriorityRule.trigger_scene == scene),
            # risk_level 匹配：NULL / '*' / '' 通配，或精确匹配
            or_(AgentPriorityRule.trigger_risk_level.is_(None),
                AgentPriorityRule.trigger_risk_level == '*',
                AgentPriorityRule.trigger_risk_level == '',
                AgentPriorityRule.trigger_risk_level == risk_level),
            # category 匹配：NULL / '*' / '' 通配，或精确匹配
            or_(AgentPriorityRule.trigger_category.is_(None),
                AgentPriorityRule.trigger_category == '*',
                AgentPriorityRule.trigger_category == '',
                AgentPriorityRule.trigger_category == cat),
        ).order_by(
            AgentPriorityRule.rule_priority.asc()
        ).all()

        logger.info(f"Loaded {len(rules)} matching rules for scene={scene}, risk={risk_level}, category={category}")
        return rules

    def _apply_priority_rules(
        self,
        nodes: List[Dict],
        rules: List[Any]
    ) -> List[Dict]:
        """应用规则覆盖 Agent priority

        规则优先级：rule_priority 大的规则优先覆盖

        Args:
            nodes: 节点列表
            rules: 匹配的规则列表

        Returns:
            更新后的节点列表
        """
        node_map = {n["agent_id"]: n for n in nodes}

        for rule in rules:
            agent_id = rule.agent_id
            if agent_id in node_map:
                node = node_map[agent_id]
                # 规则覆盖默认 priority
                node["priority"] = rule.priority
                node["priority_source"] = f"rule:{rule.id}"
                logger.debug(f"Applied rule {rule.id}: {agent_id} priority={rule.priority}")

        return nodes

    def _build_execution_batches(self, nodes: List[Dict]) -> List[Dict]:
        """按 priority 分组生成执行批次

        相同 priority 的 Agent 在同一批次并行执行，
        不同批次按 priority 升序顺序执行。

        Args:
            nodes: 节点列表

        Returns:
            执行批次列表
        """
        # 按 priority 排序
        sorted_nodes = sorted(nodes, key=lambda n: n["priority"])

        # 分组
        batches = []
        current_priority = None
        current_batch_agents = []

        for node in sorted_nodes:
            if node["priority"] != current_priority:
                if current_batch_agents:
                    batches.append({
                        "priority": current_priority,
                        "agents": current_batch_agents
                    })
                current_priority = node["priority"]
                current_batch_agents = [node["agent_id"]]
            else:
                current_batch_agents.append(node["agent_id"])

        # 最后一批次
        if current_batch_agents:
            batches.append({
                "priority": current_priority,
                "agents": current_batch_agents
            })

        return batches

    def get_current_batch(
        self,
        plan: DAGExecutionPlan,
        completed: List[str]
    ) -> List[str]:
        """获取当前可执行的 Agent（下一批次中 priority 最小且未完成）

        Args:
            plan: DAG 执行计划
            completed: 已完成的节点 ID 列表

        Returns:
            当前批次可执行的节点 ID 列表（并行执行）
        """
        completed_set = set(completed)

        for batch in plan["execution_batches"]:
            # 检查该批次是否有未完成的 Agent
            unfinished = [a for a in batch["agents"] if a not in completed_set]
            if unfinished:
                return unfinished

        return []  # 所有批次已完成

    def get_execution_order_description(self, plan: DAGExecutionPlan) -> str:
        """生成执行顺序描述（用于 SSE 事件展示）

        Args:
            plan: DAG 执行计划

        Returns:
            执行顺序描述文本
        """
        lines = []
        for i, batch in enumerate(plan["execution_batches"], 1):
            agents_str = ", ".join(batch["agents"])
            if len(batch["agents"]) > 1:
                lines.append(f"批次 {i}（priority={batch['priority']}，并行）：{agents_str}")
            else:
                lines.append(f"批次 {i}（priority={batch['priority']}）：{agents_str}")
        return "\n".join(lines)