"""
Agent 元数据解析器

从 .md 文件中解析 agent 的元数据，包括：
- name: agent 名称
- description: agent 描述
- capabilities: 能力标签列表
- skill_level: 技能等级（1-5）
- tags: 标签列表
- preferred_contexts: 首选上下文列表
"""

import os
import re
import yaml
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class AgentMetadataParser:
    """Agent 元数据解析器"""

    def __init__(self, agents_dir: str):
        """
        初始化解析器

        Args:
            agents_dir: agents 目录路径
        """
        self.agents_dir = agents_dir
        self._cache: Dict[str, Dict] = {}

    def parse(self, agent_id: str) -> Optional[Dict]:
        """
        解析指定 agent 的元数据

        Args:
            agent_id: agent ID（文件名不含扩展名）

        Returns:
            元数据字典，如果解析失败返回 None
        """
        # 检查缓存
        if agent_id in self._cache:
            return self._cache[agent_id]

        # 读取文件
        file_path = os.path.join(self.agents_dir, f'{agent_id}.md')
        if not os.path.exists(file_path):
            logger.warning(f"Agent file not found: {file_path}")
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析 YAML frontmatter
            metadata = self._parse_frontmatter(content)
            if metadata is None:
                logger.warning(f"Failed to parse frontmatter for agent: {agent_id}")
                return None

            # 添加 ID
            metadata['id'] = agent_id

            # 设置默认值
            metadata = self._apply_defaults(metadata)

            # 缓存结果
            self._cache[agent_id] = metadata

            return metadata

        except Exception as e:
            logger.error(f"Error parsing agent {agent_id}: {e}")
            return None

    def get_all_agents(self) -> List[Dict]:
        """
        获取所有 agent 的元数据

        Returns:
            元数据列表
        """
        agents = []

        if not os.path.exists(self.agents_dir):
            logger.warning(f"Agents directory not found: {self.agents_dir}")
            return agents

        # 遍历所有 .md 文件
        for filename in os.listdir(self.agents_dir):
            if filename.endswith('.md'):
                agent_id = filename[:-3]  # 去除 .md 扩展名
                metadata = self.parse(agent_id)
                if metadata:
                    agents.append(metadata)

        return agents

    def _parse_frontmatter(self, content: str) -> Optional[Dict]:
        """
        解析 YAML frontmatter

        Args:
            content: 文件内容

        Returns:
            元数据字典，如果解析失败返回 None
        """
        # 匹配 YAML frontmatter
        pattern = r'^---\s*\n(.*?)\n---\s*\n'
        match = re.match(pattern, content, re.DOTALL)

        if not match:
            return None

        yaml_content = match.group(1)

        try:
            metadata = yaml.safe_load(yaml_content)
            return metadata if isinstance(metadata, dict) else None
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {e}")
            return None

    def _apply_defaults(self, metadata: Dict) -> Dict:
        """
        应用默认值

        Args:
            metadata: 原始元数据

        Returns:
            应用默认值后的元数据
        """
        # 创建结果字典，保留原有字段
        result = metadata.copy()

        # 应用默认值
        defaults = {
            'name': 'Unknown Agent',
            'description': '',
            'capabilities': [],
            'skill_level': 3,
            'tags': [],
            'preferred_contexts': [],
            'model': 'inherit',
            'priority': 50  # 默认优先级（诊断类默认并行）
        }

        for key, default_value in defaults.items():
            if key not in result:
                result[key] = default_value

        return result

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
