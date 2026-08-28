"""
工具注册中心
定义和管理 Claude 可调用的工具
"""
import os
import json
import logging
import time
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from config import Config

logger = logging.getLogger(__name__)


@dataclass
class ToolSchema:
    """工具 Schema 定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Optional[Callable] = None
    
    def to_claude_format(self) -> Dict[str, Any]:
        """转换为 Claude API 所需的格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema
        }


class ToolHandler(ABC):
    """工具处理器基类"""
    
    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行工具

        Returns:
            Dict with 'success' and 'result' or 'error'
        """
        pass

    def _ensure_within_workspace(self, abs_path: str) -> bool:
        """校验路径位于工作空间内

        追加分隔符后比对前缀，防止 ../workspace_evil 这类共享前缀目录的绕过；
        normcase 兼容 Windows 大小写不敏感。
        """
        workspace = os.path.abspath(self.workspace_dir)
        normalized = os.path.normcase(abs_path)
        return (normalized == os.path.normcase(workspace)
                or normalized.startswith(os.path.join(os.path.normcase(workspace), '')))


class FileReadHandler(ToolHandler):
    """文件读取工具"""
    
    def __init__(self, workspace_dir: str = ""):
        self.workspace_dir = workspace_dir or Config.WORKSPACE_DIR
    
    def execute(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """读取文件内容"""
        try:
            # 安全检查：确保路径在工作空间内
            abs_path = os.path.abspath(os.path.join(self.workspace_dir, file_path))
            if not self._ensure_within_workspace(abs_path):
                return {
                    "success": False,
                    "error": "Access denied: path outside workspace"
                }
            
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }
            
            # 检查文件大小（限制 1MB）
            if os.path.getsize(abs_path) > 1024 * 1024:
                return {
                    "success": False,
                    "error": "File too large (max 1MB)"
                }
            
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                "success": True,
                "result": content
            }
        except Exception as e:
            logger.error(f"File read error: {e}")
            return {
                "success": False,
                "error": str(e)
            }


class FileWriteHandler(ToolHandler):
    """文件写入工具"""
    
    def __init__(self, workspace_dir: str = ""):
        self.workspace_dir = workspace_dir or Config.WORKSPACE_DIR
    
    def execute(self, file_path: str, content: str, **kwargs) -> Dict[str, Any]:
        """写入文件内容"""
        try:
            # 安全检查
            abs_path = os.path.abspath(os.path.join(self.workspace_dir, file_path))
            if not self._ensure_within_workspace(abs_path):
                return {
                    "success": False,
                    "error": "Access denied: path outside workspace"
                }
            
            # 确保目录存在
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "result": f"Successfully wrote to {file_path}"
            }
        except Exception as e:
            logger.error(f"File write error: {e}")
            return {
                "success": False,
                "error": str(e)
            }


class ListFilesHandler(ToolHandler):
    """列出目录文件工具"""
    
    def __init__(self, workspace_dir: str = ""):
        self.workspace_dir = workspace_dir or Config.WORKSPACE_DIR
    
    def execute(self, directory: str = "", **kwargs) -> Dict[str, Any]:
        """列出目录内容"""
        try:
            abs_path = os.path.abspath(os.path.join(self.workspace_dir, directory))
            if not self._ensure_within_workspace(abs_path):
                return {
                    "success": False,
                    "error": "Access denied: path outside workspace"
                }
            
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "error": f"Directory not found: {directory}"
                }
            
            items = []
            for item in os.listdir(abs_path):
                item_path = os.path.join(abs_path, item)
                items.append({
                    "name": item,
                    "type": "directory" if os.path.isdir(item_path) else "file",
                    "size": os.path.getsize(item_path) if os.path.isfile(item_path) else None
                })
            
            return {
                "success": True,
                "result": json.dumps(items, indent=2)
            }
        except Exception as e:
            logger.error(f"List files error: {e}")
            return {
                "success": False,
                "error": str(e)
            }


class WebSearchHandler(ToolHandler):
    """Web 搜索工具（优先级 Exa > Tavily；Exa 额度类失败后粘性退避直接走 Tavily）"""

    EVIDENCE_EXCERPT_CHAR_LIMIT = 500
    EVIDENCE_PASSAGE_CHAR_LIMIT = 4000
    # Exa 额度类失败（402/429）后的粘性退避时长（秒）：
    # 退避期内每次搜索直接使用 Tavily，避免先白打一发注定失败的 Exa 请求。
    # key 更换立即解除退避（管理员换新 key 场景）；TTL 过期后恢复尝试 Exa
    #（覆盖月度额度刷新场景，最多晚 1 小时恢复）。
    EXA_QUOTA_BACKOFF_SECONDS = 3600

    def __init__(self, exa_api_key: Optional[str] = None, tavily_api_key: Optional[str] = None):
        # Explicit values are a test seam; production reads the database per call.
        self._explicit_exa_api_key = exa_api_key
        self._explicit_tavily_api_key = tavily_api_key
        self.exa_api_key = (exa_api_key or "").strip()
        self.tavily_api_key = (tavily_api_key or "").strip()
        self._fallback_mode = None  # 'tavily' 或 None
        # 粘性退避状态：记录额度类失败发生时的 key 与到期时间，
        # key 更换后自动失效，避免对已更换的新 key 误判为额度耗尽。
        self._exa_backoff_until = 0.0
        self._exa_backoff_key = ""

    def _load_database_credentials(self) -> None:
        if self._explicit_exa_api_key is not None or self._explicit_tavily_api_key is not None:
            self.exa_api_key = (self._explicit_exa_api_key or "").strip()
            self.tavily_api_key = (self._explicit_tavily_api_key or "").strip()
            return
        from db import db
        from models import SystemConfig

        rows = db.query(SystemConfig).filter(
            SystemConfig.key.in_(("EXA_API_KEY", "TAVILY_API_KEY"))
        ).all()
        values = {row.key: row.value for row in rows}
        # strip：防御后台保存的 key 带首尾空格/换行（服务端会因此 401）
        self.exa_api_key = (values.get("EXA_API_KEY") or "").strip()
        self.tavily_api_key = (values.get("TAVILY_API_KEY") or "").strip()
    
    def _sanitize_text(self, text: str, limit: int = EVIDENCE_EXCERPT_CHAR_LIMIT) -> str:
        """清理文本中的特殊字符，确保 JSON 安全"""
        if not text:
            return ""
        # 移除控制字符
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
        # 截断过长文本
        if len(text) > limit:
            text = text[:limit] + "..."
        return text.strip()
    
    def execute(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        执行 Web 搜索
        优先级：Exa > Tavily（移除 DuckDuckGo）。
        Exa 额度类失败（402/429）后进入粘性退避，退避期内直接使用 Tavily。

        Returns:
            Dict with:
            - success: bool
            - result: str (文本格式供 Agent 使用)
            - citations: List[Dict] (结构化引用数据供前端显示)
        """
        self._load_database_credentials()
        self._fallback_mode = None

        # 1. 尝试 Exa 搜索（AI 原生搜索，质量最高）
        if self.exa_api_key and not self._exa_quota_backoff_active():
            result = self._search_exa(query)
            if result.get("success"):
                return result
            if self._is_exa_quota_error(result):
                self._mark_exa_quota_backoff()
            # Exa 失败，降级到 Tavily
            logger.warning("Exa search failed, falling back to Tavily")
            self._fallback_mode = 'tavily'

        # 2. 尝试 Tavily 搜索
        if self.tavily_api_key and self._fallback_mode in [None, 'tavily']:
            result = self._search_tavily(query)
            if result.get("success"):
                return result
            # Tavily 也失败，返回错误（移除 DuckDuckGo 降级）
            logger.error("Tavily search failed, no more fallback options")
            if self.exa_api_key:
                return {
                    "success": False,
                    "error": "All search providers failed (Exa, Tavily)"
                }
            return {
                "success": False,
                "error": "Tavily search failed and no Exa API key configured as fallback"
            }

        # 3. 无可用搜索渠道：区分"完全没配 key"与"Exa 不可用且未配置 Tavily"
        if self.exa_api_key:
            return {
                "success": False,
                "error": "Search unavailable: Exa failed or in quota backoff, and no Tavily API key configured"
            }
        return {
            "success": False,
            "error": "No search API keys configured in admin settings (Exa or Tavily required)"
        }

    @staticmethod
    def _is_exa_quota_error(result: Dict[str, Any]) -> bool:
        """识别 Exa 额度类失败：402（余额/免费额度耗尽）、429（限流/配额）。"""
        error = str(result.get("error", ""))
        return "402" in error or "429" in error or "quota" in error.lower()

    def _exa_quota_backoff_active(self) -> bool:
        """Exa 粘性退避是否生效（TTL 内且 key 未更换）。"""
        if self._exa_backoff_until <= 0.0:
            return False
        if time.monotonic() >= self._exa_backoff_until:
            return False
        return self.exa_api_key == self._exa_backoff_key

    def _mark_exa_quota_backoff(self) -> None:
        self._exa_backoff_until = time.monotonic() + self.EXA_QUOTA_BACKOFF_SECONDS
        self._exa_backoff_key = self.exa_api_key
        logger.warning(
            "Exa quota/credit exhausted; skipping Exa for %ss, calls will go straight to Tavily",
            self.EXA_QUOTA_BACKOFF_SECONDS,
        )
    
    def _search_exa(self, query: str) -> Dict[str, Any]:
        """使用 Exa API 搜索（AI 原生搜索）"""
        try:
            import requests
            
            response = requests.post(
                "https://api.exa.ai/search",
                headers={
                    "x-api-key": self.exa_api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "query": query,
                    "type": "auto",  # 自动选择搜索类型
                    "numResults": 10,
                    "contents": {
                        "text": {
                            "maxCharacters": self.EVIDENCE_PASSAGE_CHAR_LIMIT
                        }
                    }
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # 格式化搜索结果（文本格式供 Agent 使用）
                results = []
                citations = []
                evidence_items = []
                
                # 添加搜索结果
                for i, result in enumerate(data.get("results", [])[:10], 1):
                    title = self._sanitize_text(result.get('title', 'No Title'))
                    url = result.get('url', '')
                    passage = self._sanitize_text(
                        result.get('text', ''), self.EVIDENCE_PASSAGE_CHAR_LIMIT
                    )
                    text = self._sanitize_text(passage)
                    author = result.get('author', '')
                    published_date = result.get('publishedDate', '')
                    
                    # 文本格式
                    result_text = f"{i}. **{title}**\n"
                    if author:
                        result_text += f"   作者: {author}\n"
                    if published_date:
                        result_text += f"   发布日期: {published_date}\n"
                    result_text += f"   URL: {url}\n"
                    result_text += f"   {text}...\n"
                    results.append(result_text)
                    
                    # 结构化引用
                    citations.append({
                        "title": title,
                        "url": url,
                        "snippet": text,
                        "author": author,
                        "publishedDate": published_date
                    })
                    evidence_items.append({
                        "source_type": "web",
                        "source_id": url or None,
                        "title": title,
                        "url": url or None,
                        "provider": "exa",
                        "rank": i,
                        "relevance_score": result.get("score"),
                        "excerpt": text,
                        "passage": passage,
                        "locator": {},
                        "source_version": published_date or None,
                        "completeness": "passage" if passage else "unavailable",
                    })
                
                # 检查是否有自动决定搜索类型
                search_type = data.get("autoDecidedSearchType", "unknown")
                
                return {
                    "success": True,
                    "result": f"搜索结果（Exa - {search_type}）:\n\n" + "\n".join(results),
                    "citations": citations,
                    "evidence_items": evidence_items,
                }
            elif response.status_code == 429:
                # 配额用尽（限流/月度配额）
                return {
                    "success": False,
                    "error": "Exa API quota exceeded"
                }
            elif response.status_code == 402:
                # 余额/免费额度耗尽（区别于 429 限流）：需充值或等待月度刷新
                return {
                    "success": False,
                    "error": "Exa API credits exhausted (402 Payment Required) - top up at exa.ai or wait for monthly reset"
                }
            else:
                return {
                    "success": False,
                    "error": f"Exa API error: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"Exa search error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _search_tavily(self, query: str) -> Dict[str, Any]:
        """使用 Tavily API 搜索"""
        try:
            import requests
            
            response = requests.post(
                "https://api.tavily.com/search",
                headers={
                    "Authorization": f"Bearer {self.tavily_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "query": query,
                    "search_depth": "basic",
                    "include_answer": True,
                    "include_raw_content": False,
                    "max_results": 10
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # 格式化搜索结果（文本格式供 Agent 使用）
                results = []
                evidence_items = []
                
                # 添加直接回答
                if data.get("answer"):
                    results.append(f"**摘要回答**: {self._sanitize_text(data['answer'])}\n")
                
                # 添加搜索结果
                for i, result in enumerate(data.get("results", [])[:10], 1):
                    title = self._sanitize_text(result.get('title', 'No Title'))
                    url = result.get('url', '')
                    passage = self._sanitize_text(
                        result.get('content', ''), self.EVIDENCE_PASSAGE_CHAR_LIMIT
                    )
                    content = self._sanitize_text(passage)
                    results.append(
                        f"{i}. **{title}**\n"
                        f"   URL: {url}\n"
                        f"   {content}...\n"
                    )
                    if url:
                        evidence_items.append({
                            "source_type": "web",
                            "source_id": url,
                            "title": title,
                            "url": url,
                            "provider": "tavily",
                            "rank": i,
                            "relevance_score": result.get("score"),
                            "excerpt": content,
                            "passage": passage,
                            "locator": {},
                            "source_version": None,
                            "completeness": "snippet" if passage else "unavailable",
                        })
                
                # 构建结构化引用数据（供前端显示）
                citations = []
                
                # 如果有直接回答，添加为第一个引用
                if data.get("answer"):
                    citations.append({
                        "title": "AI 摘要回答",
                        "url": "",
                        "snippet": self._sanitize_text(data['answer'])
                    })
                
                # 添加搜索结果引用
                for result in data.get("results", [])[:10]:
                    title = self._sanitize_text(result.get('title', 'No Title'))
                    url = result.get('url', '')
                    content = self._sanitize_text(result.get('content', ''))
                    if url:  # 只添加有 URL 的结果
                        citations.append({
                            "title": title,
                            "url": url,
                            "snippet": content
                        })
                
                return {
                    "success": True,
                    "result": f"搜索结果（Tavily）:\n\n" + "\n".join(results),
                    "citations": citations,
                    "evidence_items": evidence_items,
                }
            elif response.status_code == 429:
                # 配额用尽
                return {
                    "success": False,
                    "error": "Tavily API quota exceeded"
                }
            elif response.status_code == 432:
                # Tavily 自定义状态码：月度用量超限（key 有效但免费额度用完）
                return {
                    "success": False,
                    "error": "Tavily usage limit exceeded (432, monthly quota used up)"
                }
            else:
                return {
                    "success": False,
                    "error": f"Tavily API error: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _search_duckduckgo(self, query: str) -> Dict[str, Any]:
        """使用 DuckDuckGo 搜索（免费，无需 API Key）"""
        try:
            import requests
            
            # 使用 DuckDuckGo Instant Answer API
            response = requests.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1
                },
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                
                results = []
                citations = []
                
                # 添加摘要
                if data.get("AbstractText"):
                    abstract_text = self._sanitize_text(data['AbstractText'])
                    results.append(f"**摘要**: {abstract_text}\n")
                    abstract_url = data.get("AbstractURL", "")
                    if abstract_url:
                        results.append(f"来源: {abstract_url}\n")
                        citations.append({
                            "title": "摘要",
                            "url": abstract_url,
                            "snippet": abstract_text
                        })
                
                # 添加相关主题
                for topic in data.get("RelatedTopics", [])[:5]:
                    if isinstance(topic, dict) and "Text" in topic:
                        sanitized_text = self._sanitize_text(topic.get('Text', ''))
                        results.append(f"- {sanitized_text}")
                        first_url = topic.get("FirstURL", "")
                        if first_url:
                            results.append(f"  URL: {first_url}")
                            # 从文本中提取标题（通常是第一个链接前的文本）
                            title = sanitized_text.split(' - ')[0] if ' - ' in sanitized_text else sanitized_text[:50]
                            citations.append({
                                "title": title,
                                "url": first_url,
                                "snippet": sanitized_text
                            })
                
                # 添加定义
                if data.get("Definition"):
                    definition_text = self._sanitize_text(data['Definition'])
                    results.append(f"\n**定义**: {definition_text}")
                    definition_url = data.get("DefinitionURL", "")
                    if definition_url:
                        results.append(f"来源: {definition_url}")
                        citations.append({
                            "title": "定义",
                            "url": definition_url,
                            "snippet": definition_text
                        })
                
                if results:
                    return {
                        "success": True,
                        "result": f"搜索结果（DuckDuckGo）:\n\n" + "\n".join(results),
                        "citations": citations
                    }
                else:
                    return {
                        "success": True,
                        "result": f"搜索结果（DuckDuckGo）: 未找到 '{query}' 的相关结果，建议尝试更具体的搜索词。",
                        "citations": []
                    }
            else:
                return {
                    "success": False,
                    "error": f"DuckDuckGo API error: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return {
                "success": False,
                "error": str(e)
            }


class ToolsRegistry:
    """工具注册中心"""
    
    def __init__(self, workspace_dir: str = ""):
        self.tools: Dict[str, ToolSchema] = {}
        self.handlers: Dict[str, ToolHandler] = {}
        self.workspace_dir = workspace_dir
        self._mcp_tools: Dict[str, str] = {}  # tool_name -> server_name mapping for MCP tools
        self._register_builtin_tools()
    
    def _register_builtin_tools(self):
        """注册内置工具"""
        
        # 文件读取工具
        self.register_tool(ToolSchema(
            name="file_read",
            description="Read the contents of a file from the workspace. Use this to examine existing files.",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to read, relative to workspace root"
                    }
                },
                "required": ["file_path"]
            }
        ))
        self.handlers["file_read"] = FileReadHandler(self.workspace_dir)
        
        # 文件写入工具
        self.register_tool(ToolSchema(
            name="file_write",
            description="Write content to a file in the workspace. Creates the file if it doesn't exist, overwrites if it does.",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to write, relative to workspace root"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["file_path", "content"]
            }
        ))
        self.handlers["file_write"] = FileWriteHandler(self.workspace_dir)
        
        # 列出文件工具
        self.register_tool(ToolSchema(
            name="list_files",
            description="List files and directories in a given path within the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory path to list, relative to workspace root. Use empty string for root."
                    }
                },
                "required": []
            }
        ))
        self.handlers["list_files"] = ListFilesHandler(self.workspace_dir)

        # Web 搜索工具
        self.register_tool(ToolSchema(
            name="web_search",
            description="Search the web for information. Returns relevant search results.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    }
                },
                "required": ["query"]
            }
        ))
        self.handlers["web_search"] = WebSearchHandler()
    
    def register_tool(self, tool: ToolSchema):
        """注册工具"""
        self.tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")
    
    def register_handler(self, tool_name: str, handler: ToolHandler):
        """注册工具处理器"""
        self.handlers[tool_name] = handler
        logger.info(f"Registered handler for tool: {tool_name}")
    
    def get_tools_for_claude(self, tool_names: List[str] = None) -> List[Dict[str, Any]]:
        """
        获取 Claude API 格式的工具列表
        
        Args:
            tool_names: 指定要获取的工具名称列表，None 表示获取所有
        
        Returns:
            List of tool definitions in Claude API format
        """
        if tool_names is None:
            return [tool.to_claude_format() for tool in self.tools.values()]
        
        return [
            self.tools[name].to_claude_format() 
            for name in tool_names 
            if name in self.tools
        ]
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有可用工具"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "source": "mcp" if tool.name in self._mcp_tools else "builtin"
            }
            for tool in self.tools.values()
        ]
    
    def register_mcp_tools(self, mcp_tools: List[Dict[str, Any]], server_name: str):
        """
        注册来自 MCP 服务器的工具
        
        Args:
            mcp_tools: MCP 工具列表
            server_name: MCP 服务器名称
        """
        for tool_data in mcp_tools:
            tool_name = tool_data["name"]
            
            # 创建工具 Schema
            tool = ToolSchema(
                name=tool_name,
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("input_schema", {})
            )
            
            # 注册工具
            self.tools[tool_name] = tool
            self._mcp_tools[tool_name] = server_name
            
            logger.info(f"Registered MCP tool: {tool_name} from {server_name}")
    
    def unregister_mcp_tools(self, server_name: str):
        """
        取消注册来自指定 MCP 服务器的工具
        
        Args:
            server_name: MCP 服务器名称
        """
        # 找到所有来自该服务器的工具
        tools_to_remove = [
            tool_name for tool_name, srv_name in self._mcp_tools.items()
            if srv_name == server_name
        ]
        
        # 移除工具
        for tool_name in tools_to_remove:
            if tool_name in self.tools:
                del self.tools[tool_name]
            if tool_name in self._mcp_tools:
                del self._mcp_tools[tool_name]
            logger.info(f"Unregistered MCP tool: {tool_name}")
    
    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具（支持内置工具和 MCP 工具）
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
        
        Returns:
            Execution result with 'success' and 'result' or 'error'
        """
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }
        
        # 检查是否是 MCP 工具
        if tool_name in self._mcp_tools:
            return self._execute_mcp_tool(tool_name, tool_input)
        
        # 内置工具
        if tool_name not in self.handlers:
            return {
                "success": False,
                "error": f"No handler for tool: {tool_name}"
            }
        
        handler = self.handlers[tool_name]
        
        try:
            logger.info(f"Executing tool: {tool_name} with input: {tool_input}")
            result = handler.execute(**tool_input)
            logger.info(f"Tool {tool_name} result: {result}")
            return result
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def _execute_mcp_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """执行 MCP 工具"""
        try:
            from services.mcp.mcp_client import get_mcp_client
            
            client = get_mcp_client()
            return client.execute_tool(tool_name, tool_input)
            
        except Exception as e:
            logger.error(f"MCP tool execution error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_all_tools_for_claude(self) -> List[Dict[str, Any]]:
        """
        获取所有工具（内置 + MCP）的 Claude API 格式定义
        """
        return [tool.to_claude_format() for tool in self.tools.values()]
    
    def sync_mcp_tools(self):
        """
        同步所有已连接 MCP 服务器的工具
        """
        try:
            from services.mcp.mcp_client import get_mcp_client
            
            client = get_mcp_client()
            
            # 获取所有 MCP 工具
            for tool_name, mcp_tool in client.tools.items():
                if tool_name not in self.tools:
                    self.tools[tool_name] = ToolSchema(
                        name=mcp_tool.name,
                        description=mcp_tool.description,
                        input_schema=mcp_tool.input_schema
                    )
                    self._mcp_tools[tool_name] = mcp_tool.server_name
                    logger.info(f"Synced MCP tool: {tool_name}")
                    
        except Exception as e:
            logger.error(f"Failed to sync MCP tools: {e}")


# 全局工具注册中心实例
_registry_instance: Optional[ToolsRegistry] = None


def get_tools_registry(workspace_dir: str = None) -> ToolsRegistry:
    """获取工具注册中心单例"""
    global _registry_instance
    
    if _registry_instance is None:
        _registry_instance = ToolsRegistry(workspace_dir or Config.WORKSPACE_DIR)
    
    return _registry_instance


def reset_tools_registry():
    """重置工具注册中心（用于测试）"""
    global _registry_instance
    _registry_instance = None
