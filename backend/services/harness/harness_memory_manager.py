"""
OpenHarness Memory Manager

封装 OpenHarness memory 系统,实现上下文保存/加载、会话保存/恢复、记忆压缩
"""
import os
import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class HarnessMemoryManager:
    """
    记忆系统管理器

    封装 OpenHarness memory 系统,提供上下文和会话的持久化能力
    """

    def __init__(self, workspace_dir: str, config: Optional[Dict] = None):
        """
        初始化记忆管理器

        Args:
            workspace_dir: 工作空间目录
            config: 配置字典(可选)
        """
        self.workspace_dir = Path(workspace_dir)
        self.config = config or {}

        # 创建记忆存储目录
        self.memory_dir = self.workspace_dir / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Memory manager initialized: memory_dir={self.memory_dir}")

    def save_context(
        self,
        conversation_id: int,
        context: Dict[str, Any],
        leader_session_id: Optional[int] = None
    ) -> None:
        """
        保存对话上下文

        Args:
            conversation_id: 对话 ID
            context: 上下文数据(messages, metadata 等)
            leader_session_id: Leader 会话 ID(可选)
        """
        conv_dir = self.memory_dir / f"conversation_{conversation_id}"
        conv_dir.mkdir(parents=True, exist_ok=True)

        context_file = conv_dir / "context.json"

        # 添加元数据
        context_to_save = {
            **context,
            "conversation_id": conversation_id,
            "leader_session_id": leader_session_id,
        }

        # 原子写入：先写入临时文件，再重命名
        temp_file_path = None
        try:
            temp_fd, temp_file_path = tempfile.mkstemp(
                suffix='.tmp',
                prefix=f'.tmp_{uuid.uuid4().hex[:8]}_',
                dir=conv_dir
            )

            # 立即关闭文件描述符（Windows 平台必需）
            os.close(temp_fd)

            # 重新打开临时文件进行写入
            with open(temp_file_path, 'w', encoding='utf-8') as f:
                json.dump(context_to_save, f, indent=2, ensure_ascii=False)

            # 原子重命名
            os.replace(temp_file_path, context_file)

        except PermissionError as e:
            logger.error(f"File locked on Windows: {context_file}")
            raise
        except Exception as e:
            logger.error(f"Failed to save context: {e}")
            raise
        finally:
            # 清理临时文件（Windows 下可能失败）
            if temp_file_path and Path(temp_file_path).exists():
                try:
                    Path(temp_file_path).unlink()
                except Exception:
                    pass  # Windows 下文件可能仍被锁定

        logger.info(f"Context saved: conversation_id={conversation_id}, messages={len(context.get('messages', []))}")

    def load_context(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        """
        加载对话上下文

        Args:
            conversation_id: 对话 ID

        Returns:
            上下文数据,不存在返回 None
        """
        context_file = self.memory_dir / f"conversation_{conversation_id}" / "context.json"

        if not context_file.exists():
            logger.debug(f"Context not found: conversation_id={conversation_id}")
            return None

        try:
            with open(context_file, 'r', encoding='utf-8') as f:
                context = json.load(f)

            logger.info(f"Context loaded: conversation_id={conversation_id}")
            return context
        except Exception as e:
            logger.error(f"Failed to load context: {e}")
            return None

    def save_session_state(
        self,
        leader_session_id: int,
        harness_session_id: str,
        session_state: Dict[str, Any]
    ) -> None:
        """
        保存会话状态

        Args:
            leader_session_id: Leader 会话 ID
            harness_session_id: OpenHarness Session ID
            session_state: 会话状态数据
        """
        session_dir = self.memory_dir / f"session_{leader_session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)

        state_file = session_dir / "state.json"

        state_to_save = {
            **session_state,
            "leader_session_id": leader_session_id,
            "harness_session_id": harness_session_id,
        }

        # 原子写入：先写入临时文件，再重命名
        temp_file_path = None
        try:
            temp_fd, temp_file_path = tempfile.mkstemp(
                suffix='.tmp',
                prefix=f'.tmp_{uuid.uuid4().hex[:8]}_',
                dir=session_dir
            )

            with open(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(state_to_save, f, indent=2, ensure_ascii=False)

            # 原子重命名
            import os
            os.replace(temp_file_path, state_file)

        except Exception as e:
            logger.error(f"Failed to save session state: {e}")
            raise
        finally:
            # 清理临时文件
            if temp_file_path and Path(temp_file_path).exists():
                try:
                    Path(temp_file_path).unlink()
                except Exception:
                    pass

        logger.info(f"Session state saved: leader_session_id={leader_session_id}")

    def load_session_state(self, leader_session_id: int) -> Optional[Dict[str, Any]]:
        """
        加载会话状态

        Args:
            leader_session_id: Leader 会话 ID

        Returns:
            会话状态数据,不存在返回 None
        """
        state_file = self.memory_dir / f"session_{leader_session_id}" / "state.json"

        if not state_file.exists():
            logger.debug(f"Session state not found: leader_session_id={leader_session_id}")
            return None

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            logger.info(f"Session state loaded: leader_session_id={leader_session_id}")
            return state
        except Exception as e:
            logger.error(f"Failed to load session state: {e}")
            return None

    def compact_memory(
        self,
        conversation_id: int,
        max_messages: int = 50
    ) -> None:
        """
        压缩记忆(保留最近 N 条消息)

        Args:
            conversation_id: 对话 ID
            max_messages: 最大保留消息数
        """
        context = self.load_context(conversation_id)

        if not context:
            logger.warning(f"Cannot compact: context not found for conversation_id={conversation_id}")
            return

        messages = context.get("messages", [])

        if len(messages) <= max_messages:
            logger.debug(f"No compaction needed: messages={len(messages)}")
            return

        # 保留最近的消息
        compacted_messages = messages[-max_messages:]

        # 创建压缩摘要
        compaction_summary = {
            "original_count": len(messages),
            "compacted_count": len(compacted_messages),
            "removed_count": len(messages) - len(compacted_messages),
        }

        # 更新上下文
        context["messages"] = compacted_messages
        context.setdefault("metadata", {})["compaction_summary"] = compaction_summary

        # 保存
        self.save_context(conversation_id, context)

        logger.info(f"Memory compacted: conversation_id={conversation_id}, removed={compaction_summary['removed_count']}")
