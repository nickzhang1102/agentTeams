"""Agent文件操作管理器

提供安全的Agent配置文件CRUD操作，包括：
- 文件创建、读取、更新、删除
- agent_id格式验证
- 路径遍历攻击防护
- YAML frontmatter解析与生成
"""

import os
import re
import yaml
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class AgentFileManager:
    """Agent配置文件管理器

    管理存储在 agents/ 目录下的Agent配置文件。
    所有操作都经过安全验证，防止路径遍历攻击。
    """

    def __init__(self, agents_dir: Optional[str] = None):
        """初始化文件管理器

        Args:
            agents_dir: Agent文件目录路径，默认从 Config.AGENTS_DIR 读取
        """
        if agents_dir:
            self.agents_dir = Path(agents_dir)
        else:
            # 从 Config 配置读取
            from config import Config
            self.agents_dir = Path(
                Config.AGENTS_DIR or
                os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'agents')
            )

        # 确保目录存在（Docker 中 agents 目录可能是只读挂载，忽略权限错误）
        try:
            self.agents_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            pass  # 只读挂载时目录已存在，无需创建

    def validate_agent_id(self, agent_id: Union[str, None]) -> bool:
        """验证agent_id格式是否合法

        合法的agent_id只能包含：
        - 字母（a-z, A-Z）
        - 数字（0-9）
        - 连字符（-）

        不允许：
        - 下划线（_）
        - 点（.）
        - 空格
        - 路径分隔符（/, \）
        - 路径遍历字符（..）

        Args:
            agent_id: 要验证的agent ID

        Returns:
            bool: 是否合法
        """
        if not agent_id or not isinstance(agent_id, str):
            return False

        # 正则验证：只允许字母、数字、连字符
        pattern = r'^[a-zA-Z0-9\-]+$'
        if not re.match(pattern, agent_id):
            return False

        # 额外安全检查：禁止路径遍历
        if '..' in agent_id or '/' in agent_id or '\\' in agent_id:
            return False

        return True

    def _validate_agent_id_detailed(self, agent_id: Union[str, None]) -> Tuple[bool, Optional[str]]:
        """验证agent_id格式并返回详细错误原因

        Args:
            agent_id: 要验证的agent ID

        Returns:
            Tuple[bool, Optional[str]]: (是否合法, 错误原因)
        """
        # 检查空值或类型错误
        if agent_id is None:
            return False, "agent_id cannot be None"
        if not isinstance(agent_id, str):
            return False, f"agent_id must be string, got {type(agent_id).__name__}"
        if not agent_id:
            return False, "agent_id cannot be empty"

        # 检查路径遍历攻击
        if '..' in agent_id:
            return False, "agent_id contains path traversal sequence '..'"
        if '/' in agent_id or '\\' in agent_id:
            return False, "agent_id contains path separators"

        # 正则验证：只允许字母、数字、连字符
        pattern = r'^[a-zA-Z0-9\-]+$'
        if not re.match(pattern, agent_id):
            # 找出非法字符
            illegal_chars = set(re.findall(r'[^a-zA-Z0-9\-]', agent_id))
            return False, f"agent_id contains illegal characters: {', '.join(repr(c) for c in sorted(illegal_chars))}"

        return True, None

    def _raise_validation_error(self, agent_id: Union[str, None]) -> None:
        """验证agent_id并在失败时抛出详细错误

        Args:
            agent_id: 要验证的agent ID

        Raises:
            ValueError: 包含详细错误原因
        """
        is_valid, error_msg = self._validate_agent_id_detailed(agent_id)
        if not is_valid:
            raise ValueError(f'Invalid agent_id: {error_msg} (got: {repr(agent_id)})')

    def create_agent_file(self, agent_id: str, metadata: Dict,
                         content: str) -> Path:
        """创建Agent配置文件

        Args:
            agent_id: Agent ID
            metadata: 元数据（将写入YAML frontmatter）
            content: Markdown内容

        Returns:
            Path: 创建的文件路径

        Raises:
            ValueError: agent_id格式非法
            IOError: 文件已存在或创建失败
        """
        # 验证agent_id
        self._raise_validation_error(agent_id)

        # 构建文件路径
        file_path = self.agents_dir / f'{agent_id}.md'

        # 检查文件是否已存在
        if file_path.exists():
            logger.warning(f'Attempted to create existing agent file: {agent_id}')
            raise IOError(f'Agent file already exists: {agent_id}')

        # 构建文件内容（YAML frontmatter + Markdown）
        file_content = self._build_file_content(metadata, content)

        # 写入文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
            logger.info(f'Created agent file: {agent_id} at {file_path}')
        except IOError as e:
            logger.error(f'Failed to create agent file {agent_id}: {e}')
            raise IOError(f'Failed to create agent file: {e}')

        return file_path

    def read_agent_file(self, agent_id: str) -> Tuple[Dict, str]:
        """读取Agent配置文件

        Args:
            agent_id: Agent ID

        Returns:
            Tuple[Dict, str]: (元数据字典, Markdown内容)

        Raises:
            ValueError: agent_id格式非法
            FileNotFoundError: 文件不存在
            IOError: 文件读取失败
        """
        # 验证agent_id
        self._raise_validation_error(agent_id)

        # 构建文件路径
        file_path = self.agents_dir / f'{agent_id}.md'

        # 检查文件是否存在
        if not file_path.exists():
            logger.warning(f'Attempted to read non-existent agent file: {agent_id}')
            raise FileNotFoundError(f'Agent file not found: {agent_id}')

        # 读取文件
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            logger.debug(f'Read agent file: {agent_id}')
        except IOError as e:
            logger.error(f'Failed to read agent file {agent_id}: {e}')
            raise IOError(f'Failed to read agent file: {e}')

        # 解析YAML frontmatter和Markdown内容
        metadata, content = self._parse_file_content(file_content)

        return metadata, content

    def update_agent_file(self, agent_id: str, metadata: Dict,
                         content: str) -> None:
        """更新Agent配置文件

        Args:
            agent_id: Agent ID
            metadata: 新的元数据
            content: 新的Markdown内容

        Raises:
            ValueError: agent_id格式非法
            FileNotFoundError: 文件不存在
            IOError: 文件更新失败
        """
        # 验证agent_id
        self._raise_validation_error(agent_id)

        # 构建文件路径
        file_path = self.agents_dir / f'{agent_id}.md'

        # 检查文件是否存在
        if not file_path.exists():
            logger.warning(f'Attempted to update non-existent agent file: {agent_id}')
            raise FileNotFoundError(f'Agent file not found: {agent_id}')

        # 构建新的文件内容
        file_content = self._build_file_content(metadata, content)

        # 写入文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
            logger.info(f'Updated agent file: {agent_id}')
        except IOError as e:
            logger.error(f'Failed to update agent file {agent_id}: {e}')
            raise IOError(f'Failed to update agent file: {e}')

    def delete_agent_file(self, agent_id: str) -> None:
        """删除Agent配置文件

        Args:
            agent_id: Agent ID

        Raises:
            ValueError: agent_id格式非法
            FileNotFoundError: 文件不存在
            IOError: 文件删除失败
        """
        # 验证agent_id
        self._raise_validation_error(agent_id)

        # 构建文件路径
        file_path = self.agents_dir / f'{agent_id}.md'

        # 检查文件是否存在
        if not file_path.exists():
            logger.warning(f'Attempted to delete non-existent agent file: {agent_id}')
            raise FileNotFoundError(f'Agent file not found: {agent_id}')

        # 删除文件
        try:
            os.remove(file_path)
            logger.info(f'Deleted agent file: {agent_id}')
        except IOError as e:
            logger.error(f'Failed to delete agent file {agent_id}: {e}')
            raise IOError(f'Failed to delete agent file: {e}')

    def _build_file_content(self, metadata: Dict, content: str) -> str:
        """构建包含YAML frontmatter的文件内容

        Args:
            metadata: 元数据字典
            content: Markdown内容

        Returns:
            str: 完整的文件内容
        """
        # 生成YAML frontmatter
        frontmatter = yaml.dump(metadata, allow_unicode=True, default_flow_style=False)

        # 组合内容
        file_content = f"---\n{frontmatter}---\n\n{content}"

        return file_content

    def _parse_file_content(self, file_content: str) -> Tuple[Dict, str]:
        """解析包含YAML frontmatter的文件内容

        Args:
            file_content: 文件内容

        Returns:
            Tuple[Dict, str]: (元数据字典, Markdown内容)
        """
        metadata = {}
        content = file_content

        # 检查是否包含frontmatter
        if file_content.startswith('---'):
            parts = file_content.split('---', 2)
            if len(parts) >= 3:
                frontmatter_text = parts[1].strip()
                content = parts[2].strip()

                # 解析YAML
                if frontmatter_text:
                    try:
                        metadata = yaml.safe_load(frontmatter_text)
                        if not isinstance(metadata, dict):
                            metadata = {}
                    except yaml.YAMLError:
                        # YAML解析失败，返回空元数据
                        metadata = {}

        return metadata, content
