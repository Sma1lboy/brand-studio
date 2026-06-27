from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zlib
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "skills" / "brand-studio" / "scripts" / "harness.py"


def load_launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("brand_studio_skill_launcher", SCRIPT_PATH)
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
        "skills": {
            "image": "gpt-image",
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


def test_default_project_paths_match_documented_layout(tmp_path: Path) -> None:
    launcher = load_launcher()

    paths = launcher.project_paths({}, tmp_path)

    assert paths["marketing_root"] == tmp_path / "assets/marketing"
    assert paths["campaigns_dir"] == tmp_path / "assets/marketing/campaigns"
    assert paths["references_dir"] == tmp_path / "assets/marketing/references"
    assert paths["plans_dir"] == tmp_path / "assets/marketing/plans"
    assert paths["asset_index"] == tmp_path / "assets/marketing/asset-state.yaml"
    assert paths["accepted_state"] == tmp_path / "assets/marketing/accepted.yaml"
    assert paths["scratch_dir"] == tmp_path / ".harness/marketing/out"
    assert paths["approved_dir"] == tmp_path / "public/marketing"


def test_project_root_option_anchors_metadata_relative_paths(tmp_path: Path) -> None:
    project = tmp_path / "product"
    other_cwd = tmp_path / "tooling"
    project.mkdir()
    other_cwd.mkdir()
    metadata_path = project / "marketing.harness.yaml"
    metadata_path.write_text(
        """
project:
  id: product
  root: .
  marketingRoot: assets/marketing
theme:
  path: assets/marketing/theme.md
campaign:
  path: assets/marketing/campaigns/launch.campaign.yaml
""".lstrip(),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--project-root",
            str(project),
            "--metadata",
            str(metadata_path),
            "plan",
        ],
        cwd=other_cwd,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert f"project_root={project.resolve()}" in completed.stdout
    assert f"marketing_root={project / 'assets/marketing'}" in completed.stdout
    assert "tooling" not in completed.stdout


def test_project_root_option_applies_without_metadata(tmp_path: Path) -> None:
    other_cwd = tmp_path / "tooling"
    project = tmp_path / "product"
    other_cwd.mkdir()
    project.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--project-root",
            str(project),
            "plan",
        ],
        cwd=other_cwd,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert f"project_root={project.resolve()}" in completed.stdout
    assert f"marketing_root={project / 'assets/marketing'}" in completed.stdout


def test_yaml_metadata_requires_pyyaml_for_lists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = load_launcher()
    metadata_path = tmp_path / "marketing.harness.yaml"
    metadata_path.write_text(
        """
project:
  id: product
sources:
  assetRoots:
    - assets/marketing
""".lstrip(),
        encoding="utf-8",
    )

    real_import = __import__

    def block_yaml_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "yaml":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", block_yaml_import)

    with pytest.raises(SystemExit) as exc:
        launcher.load_metadata(str(metadata_path))

    assert "PyYAML is required" in str(exc.value)
    assert "uv sync" in str(exc.value)


def test_launcher_resolves_to_bundled_cli() -> None:
    launcher = load_launcher()

    assert launcher.bundled_cli_command() == [
        sys.executable,
        str(ROOT / "skills/brand-studio/scripts/cli.py"),
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
        [sys.executable, str(ROOT / "skills/brand-studio/scripts/cli.py"), "--help"],
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
    size: [320, 128]
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


def test_release_render_reads_monorepo_package_changelog_and_renders(tmp_path: Path) -> None:
    project = tmp_path
    theme = project / "packages/branding/marketing/theme.md"
    changelog = project / "packages/kobe/CHANGELOG.md"
    metadata_path = project / "marketing.harness.json"
    theme.parent.mkdir(parents=True)
    changelog.parent.mkdir(parents=True)
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
      $value: clean release editorial product board
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
    (project / "package.json").write_text(
        json.dumps({"name": "test-repo", "private": True, "workspaces": ["packages/*"]}),
        encoding="utf-8",
    )
    (changelog.parent / "package.json").write_text(
        json.dumps({"name": "kobe", "version": "0.7.33"}),
        encoding="utf-8",
    )
    changelog.write_text(
        """
# Changelog

## 0.7.33

### Patch Changes

- dda80e9: Creating a task with `n` now drops you straight into the new task's engine pane.
- 9653cd7: TUI task sessions now expose tmux-native layout controls.

## 0.7.32

- Older release note that should not be used.
""".lstrip(),
        encoding="utf-8",
    )
    metadata_path.write_text(json.dumps(metadata(project)), encoding="utf-8")

    generated_campaign = (
        project / "packages/branding/marketing/campaigns/release-v0-7-33.campaign.yaml"
    )
    copy_path = project / "packages/branding/.harness/out/release-v0-7-33/copy.yaml"
    copy = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "release-copy",
            "--write",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert copy.returncode == 0, copy.stderr
    assert "release_source=changelog" in copy.stdout
    assert "changelog_count=1" in copy.stdout
    assert "copy_status=created" in copy.stdout
    copy_text = copy_path.read_text(encoding="utf-8")
    assert 'kind: "release_copy"' in copy_text
    assert 'product: "kobe"' in copy_text
    assert 'version: "0.7.33"' in copy_text
    assert 'release_theme: "Faster task starts, deeper workspace control"' in copy_text
    assert "key_points:" not in copy_text
    assert "releases:" in copy_text
    assert 'title: "Jump straight into the engine"' in copy_text
    assert 'title: "Control layouts without losing work"' in copy_text
    copy_path.write_text(
        copy_text.replace(
            'headline: "Faster task starts, deeper workspace control"',
            'headline: "Manual release headline"',
        ).replace(
            'subheadline: "kobe 0.7.33 sharpens faster task starts, deeper workspace control."',
            'subheadline: "Manual revised subheadline."',
        ),
        encoding="utf-8",
    )

    release = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "release-render",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert release.returncode == 0, release.stderr
    assert "release_source=copy" in release.stdout
    assert "changelog_count=1" in release.stdout
    assert "copy_status=existing" in release.stdout
    assert "campaign_status=created" in release.stdout
    assert "producer_skill=gpt-image" in release.stdout
    assert "producer_context=" in release.stdout
    campaign_text = generated_campaign.read_text(encoding="utf-8")
    assert 'name: "release-v0-7-33"' in campaign_text
    assert 'headline: "Manual release headline"' in campaign_text
    assert "Manual revised subheadline." in campaign_text
    assert "Creating a task with n now drops you straight" in campaign_text
    assert "TUI task sessions now expose tmux-native layout controls." in campaign_text

    output_dir = project / "packages/branding/.harness/out/release-v0-7-33"
    assert (output_dir / "release-card.svg").is_file()
    assert (output_dir / "manifest.json").is_file()
    producer_context = json.loads(
        (output_dir / "producer-context.json").read_text(encoding="utf-8")
    )
    assert producer_context["kind"] == "producer_context"
    assert producer_context["capability"] == "image"
    assert producer_context["producer_skill"] == "gpt-image"
    assert producer_context["copy"] == str(copy_path)
    assert producer_context["campaign"] == str(generated_campaign)
    assert producer_context["assets"][0]["id"] == "release-card"
    assert producer_context["assets"][0]["size"] == [1200, 640]
    release_prompt = producer_context["assets"][0]["prompt"]
    assert "Manual release headline" in release_prompt
    assert "tmux-native layout controls" in release_prompt
    assert "release notes page" in release_prompt
    assert "chronological release list" in release_prompt
    assert "The release notes are the main subject" in release_prompt
    assert "Do not make the changelog a small side panel" in release_prompt


def test_release_copy_can_include_multiple_recent_changelog_versions(tmp_path: Path) -> None:
    project = tmp_path
    theme = project / "packages/branding/marketing/theme.md"
    changelog = project / "packages/kobe/CHANGELOG.md"
    metadata_path = project / "marketing.harness.json"
    theme.parent.mkdir(parents=True)
    changelog.parent.mkdir(parents=True)
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
      $value: clean release editorial product board
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
    (project / "package.json").write_text(
        json.dumps({"name": "test-repo", "private": True, "workspaces": ["packages/*"]}),
        encoding="utf-8",
    )
    (changelog.parent / "package.json").write_text(
        json.dumps({"name": "kobe", "version": "0.7.33"}),
        encoding="utf-8",
    )
    changelog.write_text(
        """
# Changelog

## 0.7.33

### Patch Changes

- Creating a task with `n` now drops you straight into the engine pane.
- TUI task sessions now expose tmux-native layout controls.

## 0.7.32

### Patch Changes

- Web Board now renders empty Kanban columns.

## 0.7.31

### Patch Changes

- Web Board issue execution is scoped to one current project.

## 0.7.30

### Patch Changes

- Fix the workspace layout flashing on first task open.

## 0.7.29

### Patch Changes

- This older release should not be included.
""".lstrip(),
        encoding="utf-8",
    )
    metadata_path.write_text(json.dumps(metadata(project)), encoding="utf-8")

    copy = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "release-copy",
            "--write",
            "--releases",
            "4",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert copy.returncode == 0, copy.stderr
    assert "changelog_count=4" in copy.stdout
    copy_path = project / "packages/branding/.harness/out/release-v0-7-33/copy.yaml"
    copy_text = copy_path.read_text(encoding="utf-8")
    assert "key_points:" not in copy_text
    assert "releases:" in copy_text
    assert 'version: "0.7.33"' in copy_text
    assert 'version: "0.7.32"' in copy_text
    assert 'version: "0.7.31"' in copy_text
    assert 'version: "0.7.30"' in copy_text
    assert "0.7.29" not in copy_text

    release = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "release-render",
            "--force",
            "--releases",
            "4",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert release.returncode == 0, release.stderr
    producer_context = json.loads(
        (
            project
            / "packages/branding/.harness/out/release-v0-7-33/producer-context.json"
        ).read_text(encoding="utf-8")
    )
    release_prompt = producer_context["assets"][0]["prompt"]
    assert 'Version heading: "v0.7.33"' in release_prompt
    assert 'Version heading: "v0.7.32"' in release_prompt
    assert 'Version heading: "v0.7.31"' in release_prompt
    assert 'Version heading: "v0.7.30"' in release_prompt
    assert "0.7.29" not in release_prompt


def test_release_render_rejects_malformed_release_copy_rows(tmp_path: Path) -> None:
    project = tmp_path
    theme = project / "packages/branding/marketing/theme.md"
    metadata_path = project / "marketing.harness.json"
    copy_path = project / "copy.yaml"
    theme.parent.mkdir(parents=True)
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
      $value: clean release editorial product board
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
    metadata_path.write_text(json.dumps(metadata(project)), encoding="utf-8")
    copy_path.write_text(
        """
schema_version: "1.0"
kind: "release_copy"
product: "kobe"
version: "0.7.33"
release_theme: "Recent release notes"
headline: "Recent release notes"
subheadline: "kobe recent release notes."
releases:
  - package: "kobe"
    version: "0.7.33"
    changes:
      - title: "Valid row"
        detail: "This row should remain present."
  - package: "kobe"
    version: "0.7.32"
    changes:
      - title: "Missing detail row"
        source_package: "kobe"
        source_version: "0.7.32"
audience: []
visual_direction:
  mood: "release notes page"
  motifs: []
  avoid: []
sources: []
""".lstrip(),
        encoding="utf-8",
    )

    release = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "release-render",
            "--copy",
            str(copy_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert release.returncode == 1
    assert "releases[2].changes[1] requires title and detail" in release.stderr


def test_gpt_image_constraints_reject_unaligned_deliverable_size(tmp_path: Path) -> None:
    project = tmp_path
    theme = project / "assets/marketing/theme.md"
    campaign = project / "assets/marketing/campaigns/launch.campaign.yaml"
    metadata_path = project / "marketing.harness.json"
    write_theme(theme, producer_id="gpt-image")
    campaign.parent.mkdir(parents=True)
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
    size: [1001, 630]
""".lstrip(),
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(
                {
                    "project": {
                        "id": "product",
                        "root": str(project),
                        "marketingRoot": "assets/marketing",
                    },
                "theme": {
                    "path": "assets/marketing/theme.md",
                    "campaigns": "assets/marketing/campaigns",
                    "references": "assets/marketing/references",
                },
                "campaign": {"path": "assets/marketing/campaigns/launch.campaign.yaml"},
                "skills": {"image": "gpt-image"},
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "validate",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "gpt-image" in completed.stderr
    assert "multiple of 16" in completed.stderr
    assert "1008x640" in completed.stderr


def test_accept_helper_copies_candidate_and_updates_manifest_and_state(tmp_path: Path) -> None:
    project = tmp_path
    metadata_path = project / "marketing.harness.json"
    candidate = project / ".harness/marketing/out/launch/web-banner.png"
    run_lock = candidate.parent / "run.lock.json"
    plan = project / "assets/marketing/plans/launch.plan.yaml"
    write_png(candidate, width=320, height=176)
    run_lock.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "dry_run": False,
                "campaign": {"name": "launch"},
                "assets": [{"id": "web-banner", "size": [320, 176]}],
            }
        ),
        encoding="utf-8",
    )
    plan.parent.mkdir(parents=True)
    plan.write_text('schema_version: "1.0"\nid: "launch"\nstatus: "planned"\n', encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
                {
                    "project": {
                        "id": "kobe",
                        "root": str(project),
                        "marketingRoot": "assets/marketing",
                    },
                "artifacts": {
                    "scratch": ".harness/marketing/out",
                    "approved": "public/marketing",
                },
                "state": {
                    "plans": "assets/marketing/plans",
                    "assetIndex": "assets/marketing/asset-state.yaml",
                    "accepted": "assets/marketing/accepted.yaml",
                    "directoryStateFile": "asset-state.yaml",
                },
            }
        ),
        encoding="utf-8",
    )
    checksum = file_sha256(candidate)

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "accept",
            "--campaign",
            "launch",
            "--asset-id",
            "web-banner",
            "--file",
            str(candidate),
            "--checksum-sha256",
            checksum,
            "--notes",
            "Accepted from review.",
            "--tags",
            "launch,web-banner",
            "--plan",
            str(plan),
            "--update-asset-state",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    approved_file = project / "public/marketing/launch/web-banner.png"
    approved_manifest = project / "public/marketing/launch/manifest.json"
    assert approved_file.is_file()
    manifest = json.loads(approved_manifest.read_text(encoding="utf-8"))
    assert manifest["kind"] == "approved_manifest"
    assert manifest["campaign"] == "launch"
    assert manifest["assets"][0]["id"] == "web-banner"
    assert manifest["assets"][0]["mime_type"] == "image/png"
    assert manifest["assets"][0]["size"] == [320, 176]
    assert manifest["assets"][0]["checksum_sha256"] == checksum

    accepted = (project / "assets/marketing/accepted.yaml").read_text(encoding="utf-8")
    assert 'owner_kind: "repo"' not in accepted
    assert 'kind: "repo"' in accepted
    assert 'asset_id: "web-banner"' in accepted
    assert 'path: "public/marketing/launch/web-banner.png"' in accepted
    assert f'checksum_sha256: "{checksum}"' in accepted
    assert 'status: "accepted"' in plan.read_text(encoding="utf-8")
    asset_state = (project / "assets/marketing/asset-state.yaml").read_text(encoding="utf-8")
    assert 'id: "launch-web-banner"' in asset_state
    assert 'path: "public/marketing/launch/web-banner.png"' in asset_state


def test_accept_helper_rejects_checksum_mismatch(tmp_path: Path) -> None:
    project = tmp_path
    metadata_path = project / "marketing.harness.json"
    candidate = project / ".harness/marketing/out/launch/web-banner.png"
    write_png(candidate, width=320, height=176)
    metadata_path.write_text(
        json.dumps(
                {
                    "project": {
                        "id": "kobe",
                        "root": str(project),
                        "marketingRoot": "assets/marketing",
                    },
                "artifacts": {
                    "scratch": ".harness/marketing/out",
                    "approved": "public/marketing",
                },
                "state": {"accepted": "assets/marketing/accepted.yaml"},
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--metadata",
            str(metadata_path),
            "accept",
            "--campaign",
            "launch",
            "--asset-id",
            "web-banner",
            "--file",
            str(candidate),
            "--checksum-sha256",
            "0" * 64,
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "checksum mismatch" in completed.stderr
    assert not (project / "public/marketing/launch/web-banner.png").exists()


def write_theme(path: Path, *, producer_id: str = "external-producer") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
---
repo:
  id: test-repo
  name: Test Repo
version: 1.0.0
producer:
  id: {producer_id}
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
        prompt: "{{global.style-fragment.base}}"
        palette:
          - "{{global.color.primary}}"
        negative: ""
        references: []
      $type: composite
---

# Test Repo Theme
""".lstrip(),
        encoding="utf-8",
    )


def write_png(path: Path, *, width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"\x00" * (width * height * 3)
    rows = b"".join(
        b"\x00" + raw[index : index + width * 3]
        for index in range(0, len(raw), width * 3)
    )
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(
            b"IHDR",
            width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00",
        )
        + png_chunk(b"IDAT", zlib.compress(rows))
        + png_chunk(b"IEND", b"")
    )


def png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return len(data).to_bytes(4, "big") + payload + zlib.crc32(payload).to_bytes(4, "big")


def file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
