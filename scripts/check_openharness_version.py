"""检查OpenHarness版本"""
import sys

try:
    import openharness
    from importlib.metadata import version as get_version
    from packaging import version

    installed_version = get_version("openharness-ai")
    print(f"[OK] OpenHarness version: {installed_version}")

    min_version = "0.1.2"

    if version.parse(installed_version) < version.parse(min_version):
        print(f"[ERROR] Version mismatch: required >= {min_version}, got {installed_version}")
        sys.exit(1)

    print(f"[OK] Version check passed")

except ImportError:
    print("[ERROR] OpenHarness not installed")
    print("  Hint: run 'python scripts/install_openharness.py' or install manually")
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] Failed to get OpenHarness version: {e}")
    sys.exit(1)
