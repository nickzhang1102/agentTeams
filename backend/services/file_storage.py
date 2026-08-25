"""
文件存储模块
负责管理会话文件的保存、读取和版本控制
"""

import os
import mimetypes
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Optional


class FileStorage:
    """文件存储类，用于管理会话文件的存储"""

    def __init__(self, base_path: str):
        """
        初始化文件存储

        Args:
            base_path: 文件存储的基础路径
        """
        # 规范化基础路径，防止路径遍历
        self.base_path = os.path.abspath(base_path)
        # 如果基础目录不存在，则创建
        if not os.path.exists(self.base_path):
            try:
                os.makedirs(self.base_path)
            except OSError as e:
                raise IOError(f"无法创建基础存储目录: {e}")

    def _validate_path_component(self, component: str, component_name: str) -> str:
        """
        验证路径组件以防止路径遍历攻击

        Args:
            component: 要验证的路径组件
            component_name: 组件名称（用于错误消息）

        Returns:
            str: 验证后的路径组件

        Raises:
            ValueError: 如果路径组件包含非法字符
        """
        if not component:
            raise ValueError(f"{component_name}不能为空")

        # 检查路径遍历模式
        if '..' in component:
            raise ValueError(f"无效的{component_name}: 包含路径遍历字符 '..'")

        # 检查路径分隔符（Unix和Windows）
        if '/' in component or '\\' in component:
            raise ValueError(f"无效的{component_name}: 包含路径分隔符")

        # 检查空字节攻击
        if '\x00' in component:
            raise ValueError(f"无效的{component_name}: 包含空字节")

        return component

    def _validate_file_path(self, file_path: str) -> None:
        """
        验证文件路径是否在基础目录内

        使用 Path.resolve() + relative_to() 替代字符串 startswith，
        跨平台兼容正/反斜杠混用，防止路径遍历。

        Args:
            file_path: 要验证的文件路径

        Raises:
            ValueError: 如果路径在基础目录外
        """
        base = Path(self.base_path).resolve()
        target = Path(file_path).resolve()
        try:
            target.relative_to(base)
        except ValueError:
            raise ValueError("安全错误: 尝试访问基础存储目录外的路径")

    def save_file(self, conversation_id: str, message_id: str, filename: str, content: str) -> Dict:
        """
        保存文件到磁盘

        Args:
            conversation_id: 会话ID
            message_id: 消息ID
            filename: 原始文件名
            content: 文件内容

        Returns:
            dict: 包含文件元数据的字典
                - filename: 原始文件名
                - stored_filename: 存储的文件名
                - file_path: 文件完整路径
                - file_type: 文件MIME类型
                - file_size: 文件大小（字节）
                - version: 文件版本号

        Raises:
            ValueError: 如果输入参数包含非法字符
            IOError: 如果文件操作失败
        """
        # 验证输入参数，防止路径遍历攻击
        conversation_id = self._validate_path_component(conversation_id, "会话ID")
        filename = self._validate_path_component(filename, "文件名")

        # 创建会话目录
        conv_dir = os.path.join(self.base_path, conversation_id)

        # 验证会话目录路径
        self._validate_file_path(conv_dir)

        if not os.path.exists(conv_dir):
            try:
                os.makedirs(conv_dir)
            except OSError as e:
                raise IOError(f"无法创建会话目录: {e}")

        # 获取文件扩展名和MIME类型
        _, ext = os.path.splitext(filename)
        file_type = self._get_mime_type(ext)

        # 确定版本号和存储文件名（原子占位锁定，防止并发 TOCTOU 竞态覆盖）
        version, stored_filename = self._reserve_versioned_path(conv_dir, filename)

        # 构建完整文件路径
        file_path = os.path.join(conv_dir, stored_filename)

        # 验证最终文件路径
        self._validate_file_path(file_path)

        # 原子写入：先写入临时文件，再重命名覆盖占位
        temp_file_path = None
        replaced = False
        try:
            # 生成临时文件路径（同目录下）
            temp_fd, temp_file_path = tempfile.mkstemp(
                suffix='.tmp',
                prefix=f'.tmp_{uuid.uuid4().hex[:8]}_',
                dir=conv_dir
            )

            # 写入临时文件
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(content)

            # 原子重命名（覆盖已占位的最终路径，原子操作防止写入中断导致损坏）
            os.replace(temp_file_path, file_path)
            replaced = True

        except IOError as e:
            raise IOError(f"无法写入文件: {e}")
        except OSError as e:
            raise IOError(f"文件系统错误: {e}")
        finally:
            # 清理临时文件（如果重命名失败）
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass  # 忽略清理失败
            # 占位残留清理：仅当 replace 未完成时，删除本次占位文件
            if not replaced and os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                except Exception:
                    pass

        # 计算文件大小
        file_size = len(content.encode('utf-8'))

        # 返回文件元数据
        return {
            'filename': filename,
            'stored_filename': stored_filename,
            'file_path': file_path,
            'file_type': file_type,
            'file_size': file_size,
            'version': version
        }

    def save_file_binary(self, conversation_id: str, message_id: str, filename: str, content: bytes) -> Dict:
        """
        保存二进制文件到磁盘

        Args:
            conversation_id: 会话ID
            message_id: 消息ID
            filename: 原始文件名
            content: 文件内容（二进制）

        Returns:
            dict: 包含文件元数据的字典
                - filename: 原始文件名
                - stored_filename: 存储的文件名
                - file_path: 文件完整路径
                - file_type: 文件MIME类型
                - file_size: 文件大小（字节）
                - version: 文件版本号

        Raises:
            ValueError: 如果输入参数包含非法字符
            IOError: 如果文件操作失败
        """
        # 验证输入参数，防止路径遍历攻击
        conversation_id = self._validate_path_component(conversation_id, "会话ID")
        filename = self._validate_path_component(filename, "文件名")

        # 创建会话目录
        conv_dir = os.path.join(self.base_path, conversation_id)

        # 验证会话目录路径
        self._validate_file_path(conv_dir)

        if not os.path.exists(conv_dir):
            try:
                os.makedirs(conv_dir)
            except OSError as e:
                raise IOError(f"无法创建会话目录: {e}")

        # 获取文件扩展名和MIME类型
        _, ext = os.path.splitext(filename)
        file_type = self._get_mime_type(ext)

        # 确定版本号和存储文件名（原子占位锁定，防止并发 TOCTOU 竞态覆盖）
        version, stored_filename = self._reserve_versioned_path(conv_dir, filename)

        # 构建完整文件路径
        file_path = os.path.join(conv_dir, stored_filename)

        # 验证最终文件路径
        self._validate_file_path(file_path)

        # 原子写入：先写入临时文件，再重命名
        temp_file_path = None
        replaced = False
        try:
            # 生成临时文件路径（同目录下）
            temp_fd, temp_file_path = tempfile.mkstemp(
                suffix='.tmp',
                prefix=f'.tmp_{uuid.uuid4().hex[:8]}_',
                dir=conv_dir
            )

            # 写入临时文件
            with os.fdopen(temp_fd, 'wb') as f:
                f.write(content)

            # 原子重命名
            os.replace(temp_file_path, file_path)
            replaced = True

        except IOError as e:
            raise IOError(f"无法写入文件: {e}")
        except OSError as e:
            raise IOError(f"文件系统错误: {e}")
        finally:
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
            # 占位残留清理：仅当 replace 未完成时，删除本次占位文件
            if not replaced and os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                except Exception:
                    pass

        # 计算文件大小
        file_size = len(content)

        # 返回文件元数据
        return {
            'filename': filename,
            'stored_filename': stored_filename,
            'file_path': file_path,
            'file_type': file_type,
            'file_size': file_size,
            'version': version
        }

    def get_file_content(self, file_path: str) -> str:
        """
        读取文件内容

        Args:
            file_path: 文件完整路径

        Returns:
            str: 文件内容

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 路径不在基础目录内
            IOError: 文件读取失败
        """
        # 验证文件路径是否在基础目录内
        self._validate_file_path(file_path)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except IOError as e:
            raise IOError(f"无法读取文件: {e}")
        except OSError as e:
            raise IOError(f"文件系统错误: {e}")

    def get_file_content_binary(self, file_path: str) -> bytes:
        """
        读取二进制文件内容

        Args:
            file_path: 文件完整路径

        Returns:
            bytes: 文件内容（二进制）

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 路径不在基础目录内
            IOError: 文件读取失败
        """
        # 验证文件路径是否在基础目录内
        self._validate_file_path(file_path)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            with open(file_path, 'rb') as f:
                return f.read()
        except IOError as e:
            raise IOError(f"无法读取文件: {e}")
        except OSError as e:
            raise IOError(f"文件系统错误: {e}")

    def _get_mime_type(self, ext: str) -> str:
        """
        根据文件扩展名获取MIME类型

        Args:
            ext: 文件扩展名（包含点号，如 '.md'）

        Returns:
            str: MIME类型
        """
        # 自定义MIME类型映射
        mime_map = {
            '.md': 'text/markdown',
            '.py': 'text/x-python',
            '.js': 'text/javascript',
            '.vue': 'text/x-vue',
            '.html': 'text/html',
            '.css': 'text/css',
            '.json': 'application/json',
            '.txt': 'text/plain',
        }

        # 优先使用自定义映射
        if ext.lower() in mime_map:
            return mime_map[ext.lower()]

        # 使用系统mimetypes模块
        mime_type, _ = mimetypes.guess_type(f"file{ext}")
        return mime_type if mime_type else 'application/octet-stream'

    def _get_next_version(self, conv_dir: str, filename: str) -> int:
        """
        查询文件的下一个候选版本号（仅查询，存在 TOCTOU 竞态，勿单独用于写入决策）。

        Args:
            conv_dir: 会话目录路径
            filename: 原始文件名

        Returns:
            int: 下一个候选版本号
        """
        # 检查是否存在同名文件（原始文件名）
        base_file_path = os.path.join(conv_dir, filename)
        if not os.path.exists(base_file_path):
            return 1

        # 查找已存在的版本
        version = 1
        name, ext = os.path.splitext(filename)

        while True:
            version += 1
            versioned_filename = f"{name}_v{version}{ext}"
            versioned_path = os.path.join(conv_dir, versioned_filename)

            if not os.path.exists(versioned_path):
                return version

    def _reserve_versioned_path(self, conv_dir: str, filename: str) -> tuple:
        """
        原子地占用最终版本文件路径，消除并发上传同名文件时的版本号 TOCTOU 竞态。

        实现：查询候选版本号后，用 os.open(O_CREAT|O_EXCL) 原子创建占位文件；
        若占位已被并发请求抢走（FileExistsError），自增重试直到成功。
        占位文件最终会被 save_file/save_file_binary 的 os.replace 覆盖。

        Args:
            conv_dir: 会话目录路径
            filename: 原始文件名

        Returns:
            tuple: (version, stored_filename) 版本号与存储文件名
        """
        name, ext = os.path.splitext(filename)

        # 从候选版本号开始，原子抢占占位
        candidate = self._get_next_version(conv_dir, filename)
        while True:
            stored_filename = self._generate_stored_filename(filename, candidate)
            target_path = os.path.join(conv_dir, stored_filename)
            self._validate_file_path(target_path)
            try:
                # O_CREAT|O_EXCL 原子创建：成功即独占该版本路径
                fd = os.open(target_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return candidate, stored_filename
            except FileExistsError:
                # 并发请求已抢走该版本号，自增重试
                candidate += 1
                continue

    def _generate_stored_filename(self, filename: str, version: int) -> str:
        """
        生成存储的文件名

        Args:
            filename: 原始文件名
            version: 版本号

        Returns:
            str: 存储的文件名
        """
        if version == 1:
            return filename

        name, ext = os.path.splitext(filename)
        return f"{name}_v{version}{ext}"
