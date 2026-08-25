"""
测试 Leader 选队增强功能

验证 _build_agent_list_for_selection() 和 _build_selection_prompt()
的能力声明注入逻辑。
"""
import pytest
from unittest.mock import MagicMock

from leader.team_former import TeamFormer


@pytest.fixture
def team_former():
    """创建 TeamFormer 实例（mock 依赖）"""
    return TeamFormer(
        llm_service=MagicMock(),
        agent_reader=MagicMock(),
        max_tokens_limit=16384,
    )


def _make_agent(agent_id, name, desc='测试描述', capabilities=None,
                preferred_contexts=None, skill_level=3):
    """构造 agent dict（与 AgentContentReader.to_dict() 结构一致）"""
    return {
        'agent_id': agent_id,
        'name': name,
        'description': desc,
        'capabilities': capabilities or [],
        'preferred_contexts': preferred_contexts or [],
        'skill_level': skill_level,
        'tags': [],
        'category': None,
    }


# ========== _build_agent_list_for_selection ==========

class TestBuildAgentListForSelection:

    def test_agent_with_capabilities_shows_two_lines(self, team_former):
        """有 capabilities 的 Agent 输出 2 行"""
        agents = [_make_agent('a1', '专家A', capabilities=['宏观分析', '资产配置'])]
        result = team_former._build_agent_list_for_selection(agents)
        lines = result.strip().split('\n')
        assert len(lines) == 2
        assert '`a1`' in lines[0]
        assert '能力: 宏观分析, 资产配置' in lines[1]

    def test_agent_without_capabilities_shows_one_line(self, team_former):
        """无 capabilities 的 Agent 保持旧格式（1 行）"""
        agents = [_make_agent('a2', '专家B', capabilities=[])]
        result = team_former._build_agent_list_for_selection(agents)
        lines = result.strip().split('\n')
        assert len(lines) == 1
        assert '`a2`' in lines[0]

    def test_mixed_agents_correct_formatting(self, team_former):
        """混合 Agent 列表：有/无 capabilities 正确拼接"""
        agents = [
            _make_agent('a1', '专家A', capabilities=['宏观分析']),
            _make_agent('a2', '专家B', capabilities=[]),
            _make_agent('a3', '专家C', capabilities=['战略规划', '商业模式']),
        ]
        result = team_former._build_agent_list_for_selection(agents)
        lines = result.strip().split('\n')
        # 专家A: 2行, 专家B: 1行, 专家C: 2行 = 5行
        assert len(lines) == 5
        assert '能力: 宏观分析' in lines[1]
        assert '能力: 战略规划, 商业模式' in lines[4]

    def test_capability_line_includes_contexts_and_skill_level(self, team_former):
        """能力行包含适用场景和专业度"""
        agents = [_make_agent(
            'a1', '投资官',
            capabilities=['宏观分析'],
            preferred_contexts=['投资决策', '资产配置方案'],
            skill_level=4,
        )]
        result = team_former._build_agent_list_for_selection(agents)
        lines = result.strip().split('\n')
        assert len(lines) == 2
        assert '能力: 宏观分析' in lines[1]
        assert '适用: 投资决策, 资产配置方案' in lines[1]
        assert '专业度: 4/5' in lines[1]

    def test_empty_contexts_omits_context_section(self, team_former):
        """preferred_contexts 为空时省略'适用'段"""
        agents = [_make_agent(
            'a1', '专家A',
            capabilities=['分析'],
            preferred_contexts=[],
            skill_level=3,
        )]
        result = team_former._build_agent_list_for_selection(agents)
        lines = result.strip().split('\n')
        assert len(lines) == 2
        assert '能力: 分析' in lines[1]
        assert '适用' not in lines[1]
        assert '专业度: 3/5' in lines[1]

    def test_special_characters_in_capabilities(self, team_former):
        """能力描述含特殊字符不触发格式错乱"""
        agents = [_make_agent('a1', '专家A', capabilities=['C++/Java', 'SQL注入防御'])]
        result = team_former._build_agent_list_for_selection(agents)
        assert 'C++/Java' in result
        assert 'SQL注入防御' in result

    def test_long_description_truncated(self, team_former):
        """长描述截断到 80 字符"""
        long_desc = 'A' * 200
        agents = [_make_agent('a1', '专家A', desc=long_desc, capabilities=['分析'])]
        result = team_former._build_agent_list_for_selection(agents)
        lines = result.strip().split('\n')
        assert "AAA..." in lines[0]


# ========== _build_selection_prompt ==========

class TestBuildSelectionPrompt:

    def test_prompt_contains_capability_guide(self, team_former):
        """prompt 包含能力匹配指引段"""
        result = team_former._build_selection_prompt(
            '测试需求', '1. `a1` - 专家A: 描述', 'medium', False
        )
        assert '能力匹配指引' in result
        assert '优先选择"能力"字段与需求关键词匹配度高的专家' in result
        assert '无能力声明的专家仍可被选中' in result

    def test_prompt_preserves_existing_principles(self, team_former):
        """现有选择原则不变"""
        result = team_former._build_selection_prompt(
            '测试需求', '1. `a1` - 专家A: 描述', 'high', False
        )
        # 高风险非医疗场景必须包含 critic-munger
        assert 'critic-munger' in result
        # 能力匹配指引在选择原则之后
        principles_pos = result.index('选择原则')
        guide_pos = result.index('能力匹配指引')
        assert guide_pos > principles_pos

    def test_prompt_medical_high_risk_preserved(self, team_former):
        """医疗高风险场景原有原则不变"""
        result = team_former._build_selection_prompt(
            '患者胸痛', '1. `a1` - 心内科: 描述', 'high', True
        )
        assert '医疗场景的特殊性' in result
        assert '能力匹配指引' in result
