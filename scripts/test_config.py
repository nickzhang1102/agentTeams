"""测试 OpenHarness 配置加载"""
import sys
sys.path.insert(0, 'backend')

from config import Config

config = Config()
print(f"OPENHARNESS_VERSION: {config.OPENHARNESS_VERSION}")
print(f"OPENHARNESS_ENABLED: {config.OPENHARNESS_ENABLED}")
print(f"OPENHARNESS_TOOLS_ENABLED: {config.OPENHARNESS_TOOLS_ENABLED}")
print(f"OPENHARNESS_WORKSPACE: {config.OPENHARNESS_WORKSPACE}")
print(f"OPENHARNESS_TOOLS_TIMEOUT: {config.OPENHARNESS_TOOLS_TIMEOUT}")
