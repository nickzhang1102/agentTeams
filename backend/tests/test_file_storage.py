import pytest
import os
import sys
import tempfile
import shutil

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.file_storage import FileStorage


class TestFileStorage:
    """文件存储模块测试类"""

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录用于测试"""
        temp_dir = tempfile.mkdtemp()
        storage = FileStorage(temp_dir)
        yield storage
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_save_file(self, temp_storage):
        """测试保存文件"""
        conversation_id = "conv_123"
        message_id = "msg_456"
        filename = "test.md"
        content = "# Test File\nThis is a test file."

        result = temp_storage.save_file(
            conversation_id=conversation_id,
            message_id=message_id,
            filename=filename,
            content=content
        )

        # 验证返回的元数据
        assert result['filename'] == filename
        assert 'stored_filename' in result
        assert 'file_path' in result
        assert result['file_type'] == 'text/markdown'
        assert result['file_size'] == len(content.encode('utf-8'))
        assert result['version'] == 1

        # 验证文件实际存在
        assert os.path.exists(result['file_path'])

        # 验证文件内容
        with open(result['file_path'], 'r', encoding='utf-8') as f:
            saved_content = f.read()
        assert saved_content == content

    def test_get_file_content(self, temp_storage):
        """测试读取文件内容"""
        conversation_id = "conv_123"
        message_id = "msg_456"
        filename = "example.py"
        content = "def hello():\n    print('Hello, World!')"

        # 先保存文件
        save_result = temp_storage.save_file(
            conversation_id=conversation_id,
            message_id=message_id,
            filename=filename,
            content=content
        )

        # 读取文件内容
        file_path = save_result['file_path']
        retrieved_content = temp_storage.get_file_content(file_path)

        assert retrieved_content == content

    def test_multiple_versions(self, temp_storage):
        """测试同一文件名的多个版本"""
        conversation_id = "conv_123"
        message_id1 = "msg_001"
        message_id2 = "msg_002"
        message_id3 = "msg_003"
        filename = "document.md"
        content1 = "Version 1"
        content2 = "Version 2"
        content3 = "Version 3"

        # 保存第一个版本
        result1 = temp_storage.save_file(
            conversation_id=conversation_id,
            message_id=message_id1,
            filename=filename,
            content=content1
        )
        assert result1['version'] == 1
        assert result1['stored_filename'] == "document.md"

        # 保存第二个版本（相同文件名）
        result2 = temp_storage.save_file(
            conversation_id=conversation_id,
            message_id=message_id2,
            filename=filename,
            content=content2
        )
        assert result2['version'] == 2
        assert result2['stored_filename'] == "document_v2.md"

        # 保存第三个版本（相同文件名）
        result3 = temp_storage.save_file(
            conversation_id=conversation_id,
            message_id=message_id3,
            filename=filename,
            content=content3
        )
        assert result3['version'] == 3
        assert result3['stored_filename'] == "document_v3.md"

        # 验证所有文件都存在且内容正确
        content1_read = temp_storage.get_file_content(result1['file_path'])
        assert content1_read == content1

        content2_read = temp_storage.get_file_content(result2['file_path'])
        assert content2_read == content2

        content3_read = temp_storage.get_file_content(result3['file_path'])
        assert content3_read == content3

    def test_get_mime_type_markdown(self, temp_storage):
        """测试Markdown文件的MIME类型"""
        assert temp_storage._get_mime_type('.md') == 'text/markdown'

    def test_get_mime_type_python(self, temp_storage):
        """测试Python文件的MIME类型"""
        assert temp_storage._get_mime_type('.py') == 'text/x-python'

    def test_get_mime_type_javascript(self, temp_storage):
        """测试JavaScript文件的MIME类型"""
        assert temp_storage._get_mime_type('.js') == 'text/javascript'

    def test_get_mime_type_vue(self, temp_storage):
        """测试Vue文件的MIME类型"""
        assert temp_storage._get_mime_type('.vue') == 'text/x-vue'

    def test_get_mime_type_html(self, temp_storage):
        """测试HTML文件的MIME类型"""
        assert temp_storage._get_mime_type('.html') == 'text/html'

    def test_get_mime_type_css(self, temp_storage):
        """测试CSS文件的MIME类型"""
        assert temp_storage._get_mime_type('.css') == 'text/css'

    def test_get_mime_type_json(self, temp_storage):
        """测试JSON文件的MIME类型"""
        assert temp_storage._get_mime_type('.json') == 'application/json'

    def test_get_mime_type_text(self, temp_storage):
        """测试文本文件的MIME类型"""
        assert temp_storage._get_mime_type('.txt') == 'text/plain'

    def test_get_mime_type_unknown(self, temp_storage):
        """测试未知扩展名的MIME类型"""
        assert temp_storage._get_mime_type('.unknown') == 'application/octet-stream'

    def test_save_file_creates_conversation_directory(self, temp_storage):
        """测试保存文件时自动创建会话目录"""
        conversation_id = "new_conv_789"
        message_id = "msg_001"
        filename = "test.txt"
        content = "Test content"

        # 保存文件
        result = temp_storage.save_file(
            conversation_id=conversation_id,
            message_id=message_id,
            filename=filename,
            content=content
        )

        # 验证会话目录被创建
        conv_dir = os.path.join(temp_storage.base_path, conversation_id)
        assert os.path.exists(conv_dir)
        assert os.path.isdir(conv_dir)

    def test_save_file_with_unicode_content(self, temp_storage):
        """测试保存包含Unicode字符的文件"""
        conversation_id = "conv_unicode"
        message_id = "msg_001"
        filename = "unicode.txt"
        content = "你好，世界！Hello World! 🎉"

        result = temp_storage.save_file(
            conversation_id=conversation_id,
            message_id=message_id,
            filename=filename,
            content=content
        )

        # 验证文件内容
        retrieved_content = temp_storage.get_file_content(result['file_path'])
        assert retrieved_content == content

    def test_get_file_content_nonexistent_file(self, temp_storage):
        """测试读取不存在的文件"""
        nonexistent_path = os.path.join(temp_storage.base_path, "nonexistent.txt")

        with pytest.raises(FileNotFoundError):
            temp_storage.get_file_content(nonexistent_path)

    def test_save_file_with_different_conversations(self, temp_storage):
        """测试不同会话的相同文件名"""
        conversation_id1 = "conv_001"
        conversation_id2 = "conv_002"
        message_id = "msg_001"
        filename = "shared.md"
        content1 = "Content for conversation 1"
        content2 = "Content for conversation 2"

        # 保存到第一个会话
        result1 = temp_storage.save_file(
            conversation_id=conversation_id1,
            message_id=message_id,
            filename=filename,
            content=content1
        )

        # 保存到第二个会话（相同文件名）
        result2 = temp_storage.save_file(
            conversation_id=conversation_id2,
            message_id=message_id,
            filename=filename,
            content=content2
        )

        # 两个文件的版本都应该是1（不同会话独立计数）
        assert result1['version'] == 1
        assert result2['version'] == 1

        # 文件路径应该不同
        assert result1['file_path'] != result2['file_path']

        # 内容应该正确
        assert temp_storage.get_file_content(result1['file_path']) == content1
        assert temp_storage.get_file_content(result2['file_path']) == content2

    def test_init_creates_base_directory(self):
        """测试初始化时创建基础目录"""
        temp_dir = tempfile.mkdtemp()
        base_path = os.path.join(temp_dir, "storage")

        # 确保目录不存在
        assert not os.path.exists(base_path)

        # 创建FileStorage实例
        storage = FileStorage(base_path)

        # 验证目录被创建
        assert os.path.exists(base_path)
        assert os.path.isdir(base_path)

        # 清理
        shutil.rmtree(temp_dir, ignore_errors=True)

    # ==================== 安全测试 ====================

    def test_path_traversal_in_conversation_id_with_double_dots(self, temp_storage):
        """测试会话ID中的路径遍历攻击（..）"""
        with pytest.raises(ValueError, match="路径遍历"):
            temp_storage.save_file(
                conversation_id="../../etc",
                message_id="msg_001",
                filename="test.txt",
                content="malicious content"
            )

    def test_path_traversal_in_filename_with_double_dots(self, temp_storage):
        """测试文件名中的路径遍历攻击（..）"""
        with pytest.raises(ValueError, match="路径遍历"):
            temp_storage.save_file(
                conversation_id="conv_123",
                message_id="msg_001",
                filename="../../../malicious.txt",
                content="malicious content"
            )

    def test_path_traversal_in_filename_with_forward_slash(self, temp_storage):
        """测试文件名中包含正斜杠"""
        with pytest.raises(ValueError, match="路径分隔符"):
            temp_storage.save_file(
                conversation_id="conv_123",
                message_id="msg_001",
                filename="subdir/malicious.txt",
                content="malicious content"
            )

    def test_path_traversal_in_filename_with_backslash(self, temp_storage):
        """测试文件名中包含反斜杠"""
        with pytest.raises(ValueError, match="路径分隔符"):
            temp_storage.save_file(
                conversation_id="conv_123",
                message_id="msg_001",
                filename="subdir\\malicious.txt",
                content="malicious content"
            )

    def test_path_traversal_in_conversation_id_with_slash(self, temp_storage):
        """测试会话ID中包含正斜杠"""
        with pytest.raises(ValueError, match="路径分隔符"):
            temp_storage.save_file(
                conversation_id="conv/123",
                message_id="msg_001",
                filename="test.txt",
                content="malicious content"
            )

    def test_empty_conversation_id(self, temp_storage):
        """测试空会话ID"""
        with pytest.raises(ValueError, match="会话ID不能为空"):
            temp_storage.save_file(
                conversation_id="",
                message_id="msg_001",
                filename="test.txt",
                content="content"
            )

    def test_empty_filename(self, temp_storage):
        """测试空文件名"""
        with pytest.raises(ValueError, match="文件名不能为空"):
            temp_storage.save_file(
                conversation_id="conv_123",
                message_id="msg_001",
                filename="",
                content="content"
            )

    def test_null_byte_in_conversation_id(self, temp_storage):
        """测试会话ID中的空字节攻击"""
        with pytest.raises(ValueError, match="空字节"):
            temp_storage.save_file(
                conversation_id="conv\x00123",
                message_id="msg_001",
                filename="test.txt",
                content="content"
            )

    def test_null_byte_in_filename(self, temp_storage):
        """测试文件名中的空字节攻击"""
        with pytest.raises(ValueError, match="空字节"):
            temp_storage.save_file(
                conversation_id="conv_123",
                message_id="msg_001",
                filename="test\x00.txt",
                content="content"
            )

    def test_get_file_content_with_path_traversal(self, temp_storage):
        """测试读取文件时的路径遍历攻击"""
        # 创建一个临时文件在外部目录
        temp_dir = tempfile.mkdtemp()
        external_file = os.path.join(temp_dir, "external.txt")
        with open(external_file, 'w') as f:
            f.write("external content")

        try:
            # 尝试从存储外部读取文件
            with pytest.raises(ValueError, match="基础存储目录外"):
                temp_storage.get_file_content(external_file)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_conversation_id_with_multiple_path_traversals(self, temp_storage):
        """测试会话ID中包含多个路径遍历模式"""
        with pytest.raises(ValueError, match="路径遍历"):
            temp_storage.save_file(
                conversation_id="../../../../etc/passwd",
                message_id="msg_001",
                filename="test.txt",
                content="content"
            )

    def test_filename_with_multiple_path_traversals(self, temp_storage):
        """测试文件名中包含多个路径遍历模式"""
        with pytest.raises(ValueError, match="路径遍历"):
            temp_storage.save_file(
                conversation_id="conv_123",
                message_id="msg_001",
                filename="../../../../../../etc/passwd",
                content="content"
            )

    def test_combined_path_traversal_attack(self, temp_storage):
        """测试组合路径遍历攻击"""
        # 即使会话ID看起来合法，文件名中的路径遍历也应该被阻止
        with pytest.raises(ValueError, match="路径遍历"):
            temp_storage.save_file(
                conversation_id="normal_conv",
                message_id="msg_001",
                filename="../../malicious.txt",
                content="malicious content"
            )
