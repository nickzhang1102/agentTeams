"""分层上下文包，替代 enhanced_message 全文拼接。"""
from dataclasses import dataclass, field


_TASK_HISTORY_LIMIT = 6
_TASK_HISTORY_ITEM_CHAR_LIMIT = 2000
_TASK_MEMORY_LIMIT = 8
_TASK_MEMORY_ITEM_CHAR_LIMIT = 1000


def _bounded_text(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...(已截断)"


@dataclass
class ContextPack:
    """四层上下文结构，统一组装 LLM 调用所需的消息。

    Layer 1 - system_prompt:  Agent 角色定义、日期等全局信息
    Layer 2 - shared_evidence: 文件内容、搜索结果等共享证据
    Layer 3 - task_description: 用户原始需求 + 补充回答
    Layer 4 - working_memory:  对话历史摘要、前序 Agent 结果
    """

    system_prompt: str = ""
    shared_evidence: list[str] = field(default_factory=list)
    task_description: str = ""
    working_memory: list[dict] = field(default_factory=list)
    user_memory: list[str] = field(default_factory=list)

    def to_messages(self) -> list[dict]:
        """转为 OpenAI messages 格式，供 call_structured() 使用。

        Returns:
            至少含一条 user 消息的列表。
        """
        if not self.task_description:
            raise ValueError("task_description must not be empty")

        messages: list[dict] = []

        # Layer 1 + 2: system prompt + shared evidence → system message
        system_parts = []
        if self.system_prompt:
            system_parts.append(self.system_prompt)
        if self.shared_evidence:
            system_parts.append("## 相关信息\n" + "\n".join(self.shared_evidence))
        if self.user_memory:
            system_parts.append("## 用户记忆\n" + "\n".join(
                f"- {m}" for m in self.user_memory
            ))
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})

        # Layer 4: working memory → history messages
        for entry in self.working_memory:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        # Layer 3: task description → user message
        messages.append({"role": "user", "content": self.task_description})

        return messages

    def to_task_string(self) -> str:
        """转为单一 task 字符串，兼容现有 execute_agent(task=) 接口。

        Returns:
            含任务描述、共享证据、用户记忆和最近对话的有界纯文本。
        """
        if not self.task_description:
            raise ValueError("task_description must not be empty")

        parts = [self.task_description]

        if self.shared_evidence:
            parts.append("\n## 相关信息")
            for evidence in self.shared_evidence:
                parts.append(f"- {evidence}")

        if self.user_memory:
            parts.append("\n## 用户记忆")
            for memory in self.user_memory[:_TASK_MEMORY_LIMIT]:
                text = _bounded_text(memory, _TASK_MEMORY_ITEM_CHAR_LIMIT)
                if text:
                    parts.append(f"- {text}")

        valid_history = [
            entry for entry in self.working_memory
            if entry.get("role") in ("user", "assistant") and entry.get("content")
        ]
        recent_history = valid_history[-_TASK_HISTORY_LIMIT:]
        history_lines = []
        for entry in recent_history:
            role = entry.get("role")
            content = _bounded_text(entry.get("content"), _TASK_HISTORY_ITEM_CHAR_LIMIT)
            if role not in ("user", "assistant") or not content:
                continue
            label = "用户" if role == "user" else "助手"
            history_lines.append(f"- {label}: {content}")
        if history_lines:
            parts.append("\n## 最近对话")
            parts.extend(history_lines)

        return "\n".join(parts)
