from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "package_skill.py"


def load_package_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("marketing_harness_package_skill", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def zip_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def test_package_skill_writes_installable_zip(tmp_path: Path, monkeypatch) -> None:
    module = load_package_script()
    output = tmp_path / "skill.zip"
    monkeypatch.setattr(sys, "argv", ["package_skill.py", str(output)])

    assert module.main() == 0

    names = zip_names(output)
    assert "SKILL.md" in names
    assert "scripts/harness.py" in names
