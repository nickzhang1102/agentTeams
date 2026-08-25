"""测试工具执行功能"""
import sys
import os
import tempfile

# 添加 backend 到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.harness.harness_adapter import HarnessToolRegistry

def test_execute_bash_tool():
    """测试执行 bash 工具"""
    print("测试: 执行 bash 工具")

    # 创建临时工作空间
    with tempfile.TemporaryDirectory() as workspace:
        registry = HarnessToolRegistry(workspace_dir=workspace)

        # 执行简单的 bash 命令
        result = registry.execute_tool('bash', {
            'command': 'echo "Hello, OpenHarness!"',
            'timeout_seconds': 10
        })

        print(f"  成功: {result['success']}")
        print(f"  输出: {result.get('result', '').strip()}")
        print(f"  错误: {result.get('error', 'None')}")

        assert result['success'], "bash 工具应执行成功"
        assert "Hello, OpenHarness!" in result['result'], "输出应包含预期文本"

        print("  [OK] bash 工具执行成功\n")

def test_execute_read_file_tool():
    """测试执行 read_file 工具"""
    print("测试: 执行 read_file 工具")

    # 创建临时工作空间和测试文件
    with tempfile.TemporaryDirectory() as workspace:
        test_file = os.path.join(workspace, 'test.txt')
        with open(test_file, 'w') as f:
            f.write("Test content for OpenHarness")

        registry = HarnessToolRegistry(workspace_dir=workspace)

        # 执行读取文件
        result = registry.execute_tool('read_file', {
            'path': 'test.txt'
        })

        print(f"  成功: {result['success']}")
        print(f"  内容: {result.get('result', '').strip()[:50]}...")

        assert result['success'], "read_file 工具应执行成功"
        assert "Test content" in result['result'], "文件内容应包含预期文本"

        print("  [OK] read_file 工具执行成功\n")

def test_execute_write_file_tool():
    """测试执行 write_file 工具"""
    print("测试: 执行 write_file 工具")

    with tempfile.TemporaryDirectory() as workspace:
        registry = HarnessToolRegistry(workspace_dir=workspace)

        # 执行写入文件
        result = registry.execute_tool('write_file', {
            'path': 'output.txt',
            'content': 'Created by OpenHarness adapter'
        })

        print(f"  成功: {result['success']}")
        print(f"  输出: {result.get('result', '').strip()[:50]}...")

        assert result['success'], "write_file 工具应执行成功"

        # 验证文件已创建
        output_file = os.path.join(workspace, 'output.txt')
        assert os.path.exists(output_file), "文件应已创建"

        with open(output_file) as f:
            content = f.read()
            assert "Created by OpenHarness adapter" in content, "文件内容应正确"

        print("  [OK] write_file 工具执行成功\n")

def test_execute_nonexistent_tool():
    """测试执行不存在的工具"""
    print("测试: 执行不存在的工具")

    registry = HarnessToolRegistry(workspace_dir='/tmp/test')

    result = registry.execute_tool('nonexistent_tool', {})

    print(f"  成功: {result['success']}")
    print(f"  错误: {result.get('error', 'None')}")

    assert not result['success'], "不存在的工具应执行失败"
    assert "not found" in result['error'], "错误信息应说明工具不存在"

    print("  [OK] 不存在的工具正确返回错误\n")

def main():
    """运行所有测试"""
    print("=" * 60)
    print("工具执行功能测试")
    print("=" * 60)
    print()

    try:
        test_execute_bash_tool()
        test_execute_read_file_tool()
        test_execute_write_file_tool()
        test_execute_nonexistent_tool()

        print("=" * 60)
        print("[SUCCESS] 所有执行测试通过！")
        print("=" * 60)
        return 0
    except Exception as e:
        print("=" * 60)
        print(f"[FAIL] 测试失败: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
