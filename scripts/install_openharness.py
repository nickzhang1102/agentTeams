"""安装 OpenHarness 本地可编辑版本"""
import os
import subprocess
import sys
from pathlib import Path


def install_openharness():
    """安装 OpenHarness 为可编辑模式"""
    openharness_path = Path(os.environ.get('OPENHARNESS_PATH', 'D:/dev/OpenHarness'))

    if not openharness_path.exists():
        print(f"[ERROR] OpenHarness directory not found: {openharness_path}")
        print("  Please verify the OpenHarness project path")
        sys.exit(1)

    pyproject = openharness_path / "pyproject.toml"
    if not pyproject.exists():
        print(f"[ERROR] pyproject.toml not found: {pyproject}")
        sys.exit(1)

    print(f"Installing OpenHarness from {openharness_path} (editable mode)...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(openharness_path)],
            check=True,
            capture_output=True,
            text=True
        )

        print(result.stdout)
        print("[OK] OpenHarness installed successfully")

        # Verify installation
        print("\nVerifying installation...")
        script_dir = Path(__file__).parent
        check_script = script_dir / "check_openharness_version.py"
        result = subprocess.run(
            [sys.executable, str(check_script)],
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Installation failed: {e}")
        print(f"  Error output: {e.stderr}")
        sys.exit(1)


if __name__ == "__main__":
    install_openharness()
