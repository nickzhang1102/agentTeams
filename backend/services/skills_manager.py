"""
技能管理器
管理和加载 Claude 技能
Skill = 系统提示词增强 + 预设工具绑定
"""
import os
import json
import yaml
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """技能定义"""
    id: str
    name: str
    description: str
    system_prompt: str = ""
    enabled_tools: List[str] = field(default_factory=list)
    context_files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "enabled_tools": self.enabled_tools,
            "context_files": self.context_files,
            "metadata": self.metadata
        }


class SkillsManager:
    """技能管理器"""
    
    def __init__(self, skills_dir: str = "", workspace_dir: str = ""):
        """
        初始化技能管理器
        
        Args:
            skills_dir: 技能配置目录
            workspace_dir: 工作空间目录（用于读取上下文文件）
        """
        self.skills_dir = skills_dir
        self.workspace_dir = workspace_dir
        self.skills: Dict[str, Skill] = {}
        self.active_skills: List[str] = []
        
        self._load_skills()
    
    def _load_skills(self):
        """从配置目录加载技能"""
        if not self.skills_dir or not os.path.exists(self.skills_dir):
            logger.info(f"Skills directory not found: {self.skills_dir}")
            self._register_builtin_skills()
            return
        
        # 加载 YAML/JSON 配置文件
        for filename in os.listdir(self.skills_dir):
            file_path = os.path.join(self.skills_dir, filename)
            
            try:
                if filename.endswith('.yaml') or filename.endswith('.yml'):
                    skill = self._parse_yaml_skill(file_path)
                elif filename.endswith('.json'):
                    skill = self._parse_json_skill(file_path)
                elif filename.endswith('.md'):
                    skill = self._parse_markdown_skill(file_path)
                else:
                    continue
                
                if skill:
                    self.skills[skill.id] = skill
                    logger.info(f"Loaded skill: {skill.id}")
                    
            except Exception as e:
                logger.error(f"Failed to load skill from {filename}: {e}")
        
        # 注册内置技能
        self._register_builtin_skills()
    
    def _parse_yaml_skill(self, file_path: str) -> Optional[Skill]:
        """解析 YAML 格式的技能配置"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not data:
            return None
        
        skill_id = data.get('id', os.path.basename(file_path).rsplit('.', 1)[0])
        
        return Skill(
            id=skill_id,
            name=data.get('name', skill_id),
            description=data.get('description', ''),
            system_prompt=data.get('system_prompt', ''),
            enabled_tools=data.get('enabled_tools', []),
            context_files=data.get('context_files', []),
            metadata=data.get('metadata', {})
        )
    
    def _parse_json_skill(self, file_path: str) -> Optional[Skill]:
        """解析 JSON 格式的技能配置"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not data:
            return None
        
        skill_id = data.get('id', os.path.basename(file_path).rsplit('.', 1)[0])
        
        return Skill(
            id=skill_id,
            name=data.get('name', skill_id),
            description=data.get('description', ''),
            system_prompt=data.get('system_prompt', ''),
            enabled_tools=data.get('enabled_tools', []),
            context_files=data.get('context_files', []),
            metadata=data.get('metadata', {})
        )
    
    def _parse_markdown_skill(self, file_path: str) -> Optional[Skill]:
        """解析 Markdown 格式的技能配置（类似 agent 格式）"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取 frontmatter
        frontmatter = {}
        parts = None
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                fm_text = parts[1].strip()
                for line in fm_text.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        frontmatter[key.strip()] = value.strip().strip('"')

        skill_id = os.path.basename(file_path).replace('.md', '')
        # 如果有有效的 parts，使用 parts[2]；否则使用整个 content
        system_prompt = parts[2].strip() if parts and len(parts) >= 3 else content
        
        return Skill(
            id=skill_id,
            name=frontmatter.get('name', skill_id),
            description=frontmatter.get('description', ''),
            system_prompt=system_prompt,
            enabled_tools=frontmatter.get('tools', '').split(',') if frontmatter.get('tools') else [],
            context_files=frontmatter.get('context_files', '').split(',') if frontmatter.get('context_files') else [],
            metadata={}
        )
    
    def _register_builtin_skills(self):
        """注册内置技能"""
        
        # 代码助手技能
        if 'code-assistant' not in self.skills:
            self.skills['code-assistant'] = Skill(
                id='code-assistant',
                name='代码助手',
                description='专业的编程助手，支持代码编写、调试和优化',
                system_prompt="""You are an expert programming assistant. You help users with:
- Writing clean, efficient, and well-documented code
- Debugging and fixing code issues
- Code review and optimization suggestions
- Explaining complex programming concepts
- Following best practices and design patterns

When writing code, always:
1. Use clear variable and function names
2. Add appropriate comments
3. Handle errors gracefully
4. Follow the language's conventions and idioms""",
                enabled_tools=['file_read', 'file_write', 'glob', 'bash', 'grep', 'web_search']
            )
        
        # 文件管理技能
        if 'file-manager' not in self.skills:
            self.skills['file-manager'] = Skill(
                id='file-manager',
                name='文件管理',
                description='文件和目录管理专家',
                system_prompt="""You are a file management assistant. You help users with:
- Organizing files and directories
- Reading and analyzing file contents
- Creating and modifying files
- Searching for files and content

Always ensure file operations are safe and ask for confirmation before potentially destructive operations.""",
                enabled_tools=['file_read', 'file_write', 'glob', 'grep']
            )
        
        # 研究助手技能
        if 'research-assistant' not in self.skills:
            self.skills['research-assistant'] = Skill(
                id='research-assistant',
                name='研究助手',
                description='信息收集和分析助手',
                system_prompt="""You are a research assistant. You help users with:
- Gathering information on topics
- Analyzing and summarizing data
- Creating reports and documentation
- Web research and fact-checking

Always cite sources and be thorough in your research.""",
                enabled_tools=['web_search', 'file_read', 'file_write']
            )
    
    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """获取技能"""
        return self.skills.get(skill_id)
    
    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有技能"""
        return [skill.to_dict() for skill in self.skills.values()]
    
    def activate_skill(self, skill_id: str) -> bool:
        """激活技能"""
        if skill_id not in self.skills:
            return False
        
        if skill_id not in self.active_skills:
            self.active_skills.append(skill_id)
            logger.info(f"Activated skill: {skill_id}")
        
        return True
    
    def deactivate_skill(self, skill_id: str) -> bool:
        """停用技能"""
        if skill_id in self.active_skills:
            self.active_skills.remove(skill_id)
            logger.info(f"Deactivated skill: {skill_id}")
            return True
        return False
    
    def get_active_skills(self) -> List[Skill]:
        """获取当前激活的技能"""
        return [self.skills[sid] for sid in self.active_skills if sid in self.skills]
    
    def get_active_tools(self) -> List[str]:
        """获取激活技能的所有工具"""
        tools = set()
        for skill in self.get_active_skills():
            tools.update(skill.enabled_tools)
        return list(tools)
    
    def build_system_prompt_enhancement(self) -> str:
        """构建激活技能的系统提示增强"""
        active_skills = self.get_active_skills()
        
        if not active_skills:
            return ""
        
        prompt_parts = ["\n\n## Active Skills\n"]
        prompt_parts.append("The following skills are active for this conversation:\n")
        
        for skill in active_skills:
            prompt_parts.append(f"\n### {skill.name}\n")
            if skill.system_prompt:
                prompt_parts.append(skill.system_prompt)
                prompt_parts.append("\n")
        
        return "".join(prompt_parts)
    
    def load_context_files(self) -> Dict[str, str]:
        """加载激活技能的上下文文件

        安全：所有 context_file 路径必须解析后落在 workspace_dir 内，防止路径遍历。
        """
        contexts = {}

        if not self.workspace_dir:
            # 未配置工作空间，禁止加载以避免越界访问
            logger.warning("workspace_dir 未配置，跳过 context_files 加载")
            return contexts

        workspace_abs = os.path.abspath(self.workspace_dir)

        for skill in self.get_active_skills():
            for file_path in skill.context_files:
                if not file_path:
                    continue
                try:
                    full_path = os.path.abspath(os.path.join(workspace_abs, file_path))
                    # 路径遍历检查：归一化后必须严格位于 workspace 内（用 os.sep 避免前缀冲突）
                    if full_path != workspace_abs and not full_path.startswith(workspace_abs + os.sep):
                        logger.error(f"拒绝访问 workspace 外的 context file: {file_path}")
                        continue
                    if os.path.exists(full_path) and os.path.isfile(full_path):
                        with open(full_path, 'r', encoding='utf-8') as f:
                            contexts[file_path] = f.read()
                except Exception as e:
                    logger.error(f"Failed to load context file {file_path}: {e}")

        return contexts


# 全局技能管理器实例
_manager_instance: Optional[SkillsManager] = None


def get_skills_manager(skills_dir: str = None, workspace_dir: str = None) -> SkillsManager:
    """获取技能管理器单例"""
    global _manager_instance
    
    if _manager_instance is None:
        _manager_instance = SkillsManager(skills_dir or "", workspace_dir or "")
    
    return _manager_instance


def reset_skills_manager():
    """重置技能管理器（用于测试）"""
    global _manager_instance
    _manager_instance = None