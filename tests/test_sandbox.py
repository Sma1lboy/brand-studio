from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVE = ROOT / "tests" / "sandbox" / "drive.py"


def test_sandbox_drive_full_lifecycle() -> None:
    # Exercises validate -> dry-run render -> stub produce -> settle (image +
    # multimodal copy) -> report. This is the only coverage of the produce+settle
    # loop; dry-run alone never reaches settle.
    result = subprocess.run(
        [sys.executable, str(DRIVE)], capture_output=True, text=True
    )
    assert result.returncode == 0, f"sandbox drive failed:\n{result.stdout}\n{result.stderr}"
    assert "PASS:" in result.stdout
