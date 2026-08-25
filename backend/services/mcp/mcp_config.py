"""
MCP 配置管理
加载和管理 MCP 服务器配置
"""
import os
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class McpServerConfig:
    """MCP 服务器配置"""
    name: str
    transport: str  # "stdio" 或 "sse"
    command: Optional[str] = None  # stdio 模式的命令
    args: List[str] = field(default_factory=list)  # 命令参数
    url: Optional[str] = None  # sse 模式的 URL
    env: Dict[str, str] = field(default_factory=dict)  # 环变量子进程用
    headers: Dict[str, str] = field(default_factory=dict)  # HTTP headers（SSE/HTTP 传输用）
    disabled: bool = False

    def __post_init__(self) -> None:
        # Exa's credential is database-managed. Drop legacy file-backed copies
        # as soon as configuration is loaded so they cannot be returned or saved.
        if self.name == 'exa':
            self.env = dict(self.env or {})
            self.env.pop('EXA_API_KEY', None)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": self.args,
            "url": self.url,
            "env": self.env,
            "headers": self.headers,
            "disabled": self.disabled
        }


class McpConfigManager:
    """MCP 配置管理器"""
    
    # 默认配置文件路径
    DEFAULT_CONFIG_FILE = "mcp_settings.json"
    
    def __init__(self, config_path: str = None):
        """
        初始化 MCP 配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), 
            self.DEFAULT_CONFIG_FILE
        )
        self.servers: Dict[str, McpServerConfig] = {}
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        if not os.path.exists(self.config_path):
            logger.info(f"MCP config file not found: {self.config_path}")
            self._create_default_config()
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            servers_config = config.get('mcpServers', {})
            
            for name, server_data in servers_config.items():
                server = McpServerConfig(
                    name=name,
                    transport=server_data.get('transport', 'stdio'),
                    command=server_data.get('command'),
                    args=server_data.get('args', []),
                    url=server_data.get('url'),
                    env=server_data.get('env', {}),
                    headers=server_data.get('headers', {}),
                    disabled=server_data.get('disabled', False)
                )
                self.servers[name] = server
                logger.info(f"Loaded MCP server config: {name}")
                
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
    
    def _create_default_config(self):
        """创建默认配置文件"""
        default_config = {
            "mcpServers": {
                "example-stdio": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@example/mcp-server"],
                    "env": {},
                    "disabled": True
                },
                "example-sse": {
                    "transport": "sse",
                    "url": "http://localhost:3000/sse",
                    "disabled": True
                },
                "graphify": {
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "graphify.serve"],
                    "env": {},
                    "disabled": True  # 默认禁用，需图谱存在后启用
                }
            }
        }
        
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2)
            logger.info(f"Created default MCP config: {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to create default MCP config: {e}")
    
    def get_server(self, name: str) -> Optional[McpServerConfig]:
        """获取服务器配置"""
        return self.servers.get(name)
    
    def list_servers(self) -> List[Dict[str, Any]]:
        """列出所有服务器配置"""
        return [server.to_dict() for server in self.servers.values()]
    
    def list_enabled_servers(self) -> List[McpServerConfig]:
        """列出启用的服务器"""
        return [s for s in self.servers.values() if not s.disabled]
    
    def enable_server(self, name: str) -> bool:
        """启用服务器"""
        if name in self.servers:
            self.servers[name].disabled = False
            return True
        return False
    
    def disable_server(self, name: str) -> bool:
        """禁用服务器"""
        if name in self.servers:
            self.servers[name].disabled = True
            return True
        return False
    
    def add_server(self, config: McpServerConfig) -> bool:
        """添加服务器配置"""
        if config.name in self.servers:
            return False
        self.servers[config.name] = config
        return True
    
    def remove_server(self, name: str) -> bool:
        """移除服务器配置"""
        if name in self.servers:
            del self.servers[name]
            return True
        return False
    
    def save_config(self) -> bool:
        """保存配置到文件"""
        try:
            config = {
                "mcpServers": {
                    name: {
                        "transport": server.transport,
                        "command": server.command,
                        "args": server.args,
                        "url": server.url,
                        "env": server.env,
                        "headers": server.headers,
                        "disabled": server.disabled
                    }
                    for name, server in self.servers.items()
                }
            }
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"Saved MCP config to {self.config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save MCP config: {e}")
            return False


# 全局配置管理器实例
_config_instance: Optional[McpConfigManager] = None


def get_mcp_config(config_path: str = None) -> McpConfigManager:
    """获取 MCP 配置管理器单例"""
    global _config_instance
    
    if _config_instance is None:
        _config_instance = McpConfigManager(config_path)
    
    return _config_instance


def reset_mcp_config():
    """重置 MCP 配置管理器（用于测试）"""
    global _config_instance
    _config_instance = None


# 预置 MCP 服务模板。带 credential_setting_key 的服务需先在系统设置配置凭据。
PRESET_MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    "exa": {
        "name": "exa",
        "description": "Exa AI Web Search - 获取实时新闻和网络搜索数据",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@anthropic-ai/mcp-server-exa"],
        # EXA_API_KEY is injected from encrypted SystemConfig at process start.
        # Never persist the credential in mcp_settings.json.
        "env": {},
        "credential_setting_key": "EXA_API_KEY",
        "disabled": True,
        "category": "search",
    },
    "graphify": {
        "name": "graphify",
        "description": "知识图谱查询服务 - Agent 可查询已提取的知识图谱",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "graphify.serve"],  # 启动后动态注入路径
        "env": {},
        "disabled": True,  # 默认禁用，需图谱存在后启用
        "category": "knowledge",
    },
}
