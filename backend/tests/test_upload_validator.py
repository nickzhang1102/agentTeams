"""upload_validator 单元测试

覆盖校验模块的主要场景：
- 正常上传
- 扩展名拒绝
- 双重扩展名攻击
- 大小超限
- MIME 不匹配
- 重复检测
"""

import pytest
from unittest.mock import MagicMock, patch


class TestValidateUpload:
    """validate_upload 函数测试"""

    def test_valid_pdf_upload(self):
        """测试正常 PDF 上传"""
        from utils.upload_validator import validate_upload, ValidationResult

        file_content = b'%PDF-1.4 fake pdf content'

        result = validate_upload(file_content, 'test.pdf', check_duplicate=False)

        assert result.valid
        assert result.file_ext == '.pdf'
        assert result.is_binary
        assert result.content_hash is not None
        assert len(result.content_hash) == 32

    def test_valid_md_upload(self):
        """测试正常 Markdown 上传"""
        from utils.upload_validator import validate_upload

        file_content = b'# Test Document\nThis is a test.'

        result = validate_upload(file_content, 'test.md', check_duplicate=False)

        assert result.valid
        assert result.file_ext == '.md'
        assert not result.is_binary

    def test_valid_docx_upload(self):
        """测试正常 docx 上传"""
        from utils.upload_validator import validate_upload

        file_content = b'fake docx content'

        result = validate_upload(file_content, 'test.docx', check_duplicate=False)

        assert result.valid
        assert result.file_ext == '.docx'
        assert result.is_binary

    def test_no_extension(self):
        """测试文件名无扩展名"""
        from utils.upload_validator import validate_upload

        result = validate_upload(b'test content', 'testfile', check_duplicate=False)

        assert not result.valid
        assert result.error_code == 'invalid_extension'
        assert '缺少扩展名' in result.error

    def test_invalid_extension(self):
        """测试不支持扩展名"""
        from utils.upload_validator import validate_upload

        result = validate_upload(b'test content', 'test.exe', check_duplicate=False)

        assert not result.valid
        assert result.error_code == 'invalid_extension'
        assert '.exe' in result.error

    def test_video_extension_rejected(self):
        """测试视频格式被拒绝"""
        from utils.upload_validator import validate_upload

        result = validate_upload(b'fake video content', 'test.mp4', check_duplicate=False)

        assert not result.valid
        assert result.error_code == 'invalid_extension'
        assert '.mp4' in result.error

    def test_double_extension_attack(self):
        """测试双重扩展名攻击"""
        from utils.upload_validator import validate_upload

        result = validate_upload(b'test content', 'malicious.php.pdf', check_duplicate=False)

        assert not result.valid
        assert result.error_code == 'dangerous_double_ext'
        assert '.php' in result.error

    def test_double_extension_exe(self):
        """测试 .exe 双重扩展名"""
        from utils.upload_validator import validate_upload

        result = validate_upload(b'test content', 'virus.exe.pdf', check_duplicate=False)

        assert not result.valid
        assert result.error_code == 'dangerous_double_ext'
        assert '.exe' in result.error

    def test_safe_double_extension(self):
        """测试安全双重扩展名（中间不是危险类型）"""
        from utils.upload_validator import validate_upload

        result = validate_upload(b'test content', 'backup.backup.pdf', check_duplicate=False)

        assert result.valid
        assert result.file_ext == '.pdf'

    def test_size_limit_exceeded(self):
        """测试文件大小超限"""
        from utils.upload_validator import validate_upload, MAX_UPLOAD_SIZE

        large_content = b'x' * (MAX_UPLOAD_SIZE + 1)

        result = validate_upload(large_content, 'large.pdf', check_duplicate=False)

        assert not result.valid
        assert result.error_code == 'too_large'
        assert result.file_size == MAX_UPLOAD_SIZE + 1

    def test_empty_file_allowed(self):
        """测试空文件允许上传"""
        from utils.upload_validator import validate_upload

        result = validate_upload(b'', 'empty.txt', check_duplicate=False)

        assert result.valid
        assert result.file_size == 0

    def test_duplicate_detection(self):
        """测试重复检测"""
        from utils.upload_validator import validate_upload

        file_content = b'same content'

        mock_session = MagicMock()
        mock_doc = MagicMock()
        mock_doc.id = 123
        mock_session.query.return_value.filter.return_value.first.return_value = mock_doc

        result = validate_upload(file_content, 'duplicate.txt', check_duplicate=True, db_session=mock_session)

        assert not result.valid
        assert result.error_code == 'duplicate'
        assert result.duplicate_doc_id == 123

    def test_no_duplicate_found(self):
        """测试无重复文件"""
        from utils.upload_validator import validate_upload

        file_content = b'unique content'

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = validate_upload(file_content, 'unique.txt', check_duplicate=True, db_session=mock_session)

        assert result.valid
        assert result.duplicate_doc_id is None

    def test_check_duplicate_disabled(self):
        """测试关闭重复检测"""
        from utils.upload_validator import validate_upload

        result = validate_upload(b'some content', 'test.txt', check_duplicate=False)

        assert result.valid


class TestComputeContentHash:
    """compute_content_hash 函数测试"""

    def test_hash_consistency(self):
        """测试哈希一致性"""
        from utils.upload_validator import compute_content_hash

        content = b'test content'

        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)

        assert hash1 == hash2
        assert len(hash1) == 32

    def test_hash_uniqueness(self):
        """测试不同内容哈希不同"""
        from utils.upload_validator import compute_content_hash

        hash1 = compute_content_hash(b'content A')
        hash2 = compute_content_hash(b'content B')

        assert hash1 != hash2

    def test_empty_file_hash(self):
        """测试空文件哈希"""
        from utils.upload_validator import compute_content_hash

        empty_hash = compute_content_hash(b'')
        assert empty_hash == 'd41d8cd98f00b204e9800998ecf8427e'


class TestMimeValidation:
    """MIME 类型验证测试"""

    def test_mime_mismatch_detected(self):
        """测试 MIME 类型不匹配"""
        from utils.upload_validator import validate_upload

        fake_exe = b'MZ\x90\x00\x03\x00\x00\x00' + b'x' * 100

        with patch('utils.upload_validator._validate_mime_type') as mock_mime:
            mock_mime.return_value = (False, '文件内容类型不匹配: application/x-dosexec')

            result = validate_upload(fake_exe, 'fake.pdf', check_duplicate=False)

            assert not result.valid
            assert result.error_code == 'mime_mismatch'

    def test_mime_check_skip_when_magic_not_installed(self):
        """测试 python-magic 未安装时跳过 MIME 检查"""
        from utils.upload_validator import _validate_mime_type

        valid, error = _validate_mime_type(b'test content', '.txt')
        assert valid
        assert error is None


class TestConstants:
    """常量配置测试"""

    def test_allowed_extensions_coverage(self):
        """测试白名单覆盖 graphify 支持格式"""
        from utils.upload_validator import KNOWLEDGE_ALLOWED_EXTENSIONS

        assert '.py' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.ts' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.js' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.vue' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.go' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.md' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.txt' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.pdf' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.png' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.jpg' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.docx' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.xlsx' in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.mp4' not in KNOWLEDGE_ALLOWED_EXTENSIONS
        assert '.mov' not in KNOWLEDGE_ALLOWED_EXTENSIONS

    def test_binary_extensions(self):
        """测试二进制文件类型"""
        from utils.upload_validator import KNOWLEDGE_BINARY_EXTENSIONS

        assert '.pdf' in KNOWLEDGE_BINARY_EXTENSIONS
        assert '.docx' in KNOWLEDGE_BINARY_EXTENSIONS
        assert '.png' in KNOWLEDGE_BINARY_EXTENSIONS
        assert '.txt' not in KNOWLEDGE_BINARY_EXTENSIONS
        assert '.md' not in KNOWLEDGE_BINARY_EXTENSIONS

    def test_dangerous_extensions(self):
        """测试危险扩展名黑名单"""
        from utils.upload_validator import DANGEROUS_EXTENSIONS

        assert '.php' in DANGEROUS_EXTENSIONS
        assert '.exe' in DANGEROUS_EXTENSIONS
        assert '.bat' in DANGEROUS_EXTENSIONS
        assert '.jsp' in DANGEROUS_EXTENSIONS
