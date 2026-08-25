"""Locale-aware product descriptions for registered system tools."""

import logging

from utils.locale_utils import SupportedLocale


logger = logging.getLogger(__name__)
TOOL_SOURCE_LOCALE: SupportedLocale = 'en-US'

TOOL_DESCRIPTIONS_ZH_CN: dict[str, dict[str, str]] = {
    'bash': {
        'description': '在本地仓库中执行 Shell 命令。',
        'detailed_description': '执行 Shell 命令，捕获 stdout/stderr 输出。',
    },
    'read': {
        'description': '读取本地仓库中的文本文件。',
        'detailed_description': '读取 UTF-8 文本文件并显示行号。',
    },
    'write': {
        'description': '在本地仓库中创建或覆盖文本文件。',
        'detailed_description': '写入完整文件内容。',
    },
    'edit': {
        'description': '通过字符串替换编辑已有文件。',
        'detailed_description': '替换已有文件中的文本。',
    },
    'glob': {
        'description': '按 glob 模式列出匹配的文件。',
        'detailed_description': '按 glob 模式列出匹配的文件。',
    },
    'grep': {
        'description': '用正则表达式搜索文件内容。',
        'detailed_description': '用正则搜索文本文件内容。',
    },
    'web_fetch': {
        'description': '抓取一个网页，返回精简可读文本。',
        'detailed_description': '抓取一个网页，返回精简文本摘要。',
    },
    'web_search': {
        'description': '网络搜索，返回精简的顶部结果（含标题、URL、摘要）。',
        'detailed_description': '执行网络搜索，返回精简顶部结果。',
    },
    'send_message': {
        'description': '向正在运行的本地 Agent 任务发送后续消息。',
        'detailed_description': '向正在运行的本地 Agent 任务发送消息。',
    },
    'task_create': {
        'description': '创建后台 Shell 或本地 Agent 任务。',
        'detailed_description': '创建后台任务。',
    },
    'task_get': {
        'description': '获取后台任务的详细信息。',
        'detailed_description': '返回后台任务的详细状态。',
    },
    'task_list': {
        'description': '列出后台任务。',
        'detailed_description': '列出后台任务。',
    },
    'task_stop': {
        'description': '停止后台任务。',
        'detailed_description': '停止后台任务。',
    },
    'task_update': {
        'description': '更新任务描述、进度或状态备注。',
        'detailed_description': '更新任务元数据，用于进度追踪。',
    },
    'task_output': {
        'description': '读取后台任务的输出日志。',
        'detailed_description': '读取后台任务的输出。',
    },
    'sleep': {
        'description': '短暂休眠。',
        'detailed_description': '短暂暂停执行。',
    },
    'agent': {
        'description': '启动一个本地后台 Agent 任务。',
        'detailed_description': '启动本地 Agent 子进程。',
    },
    'skill': {
        'description': '按名称读取内置、用户、项目或插件技能。',
        'detailed_description': '返回已加载技能的内容。',
    },
    'ask_user_question': {
        'description': '向交互用户追问并返回答案。',
        'detailed_description': '向交互用户提问并返回答案。',
    },
    'cron_create': {
        'description': '用标准 cron 表达式创建或替换本地定时任务。使用 `oh cron start` 启动调度守护进程。',
        'detailed_description': '创建或替换本地定时任务。',
    },
    'cron_list': {
        'description': '列出已配置的本地定时任务（含计划、状态、下次运行时间）。',
        'detailed_description': '列出本地定时任务。',
    },
    'cron_delete': {
        'description': '按名称删除本地定时任务。',
        'detailed_description': '删除本地定时任务。',
    },
    'cron_toggle': {
        'description': '按名称启用或禁用本地定时任务。',
        'detailed_description': '启用或禁用本地定时任务。',
    },
    'team_create': {
        'description': '为 Agent 任务创建轻量级内存团队。',
        'detailed_description': '创建内存团队。',
    },
    'team_delete': {
        'description': '删除内存团队。',
        'detailed_description': '删除内存团队。',
    },
    'tool_search': {
        'description': '按名称或描述搜索可用工具列表。',
        'detailed_description': '搜索工具注册表内容。',
    },
    'brief': {
        'description': '将文本缩短以便精简显示。',
        'detailed_description': '返回文本的缩短版本。',
    },
    'config': {
        'description': '读取或更新 OpenHarness 设置。',
        'detailed_description': '读取或更新 OpenHarness 设置。',
    },
    'enter_worktree': {
        'description': '创建 Git worktree 并返回其路径。',
        'detailed_description': '创建 Git worktree。',
    },
    'exit_worktree': {
        'description': '按路径移除 Git worktree。',
        'detailed_description': '移除 Git worktree。',
    },
    'todo_write': {
        'description': '在 Markdown 清单文件中添加新 TODO 项或将已有项标记为完成。',
        'detailed_description': '在 TODO Markdown 文件中添加或更新条目。',
    },
    'enter_plan_mode': {
        'description': '将权限模式切换为计划模式。',
        'detailed_description': '将设置权限模式切换为计划模式。',
    },
    'exit_plan_mode': {
        'description': '将权限模式切换回默认模式。',
        'detailed_description': '将设置权限模式切换回默认。',
    },
    'notebook_edit': {
        'description': '创建或编辑 Jupyter Notebook 单元格。',
        'detailed_description': '编辑 Notebook 单元格（无需 nbformat）。',
    },
    'image_generation': {
        'description': '使用可配置的图像生成提供方生成或编辑光栅图像。适用于照片、插画、精灵图、样机、透明抠图或本地图片编辑。',
        'detailed_description': '生成或编辑光栅图像并保存到本地文件。',
    },
    'image_to_text': {
        'description': '使用视觉模型将图像转换为详细文本描述。当需要理解图像内容但当前模型不支持图像输入时使用。',
        'detailed_description': '使用多模态模型描述图像并返回文本。',
    },
    'remote_trigger': {
        'description': '立即触发已配置的本地定时任务。',
        'detailed_description': '立即运行已注册的定时任务。',
    },
    'list_mcp_resources': {
        'description': '列出已连接服务器可用的 MCP 资源。',
        'detailed_description': '列出已连接服务器发现的 MCP 资源。',
    },
    'read_mcp_resource': {
        'description': '按服务器和 URI 读取 MCP 资源。',
        'detailed_description': '从 MCP 服务器读取一个资源。',
    },
    'lsp': {
        'description': '检查当前工作区中 Python 代码的符号、定义、引用和悬浮信息。',
        'detailed_description': 'Python 源文件的只读代码智能分析。',
    },
    'mcp_auth': {
        'description': '为 MCP 服务器配置认证信息，并在可能时重连活跃会话。',
        'detailed_description': '为某个 MCP 服务器持久化认证设置。',
    },
}


def localize_tool_description(tool: dict, locale: SupportedLocale = 'zh-CN') -> dict:
    """Resolve known descriptions while preserving registry source as fallback."""
    result = dict(tool)
    tool_name = result.get('name')
    translation = TOOL_DESCRIPTIONS_ZH_CN.get(tool_name)

    if locale == 'zh-CN' and translation:
        result['description'] = translation.get('description', result.get('description', ''))
        if translation.get('detailed_description') and 'detailed_description' in result:
            result['detailed_description'] = translation['detailed_description']
    elif locale == 'zh-CN' and tool_name:
        logger.warning('tool_description_missing tool_name=%s locale=%s', tool_name, locale)

    return result
