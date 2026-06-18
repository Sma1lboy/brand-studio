# Marketing Harness

[English](README.md)

这是一个生图 harness：把品牌风格锁定为单一可信源，项目只提交“这次要表达什么”，系统统一通过本地 GPT Image skill/CLI 调图像生成，产出风格一致的宣发物料，并发布为带版本的 artifact 供项目消费。

推荐使用方式是：harness 作为全局 agent skill 安装一次；每个业务 repo 自己维护
`workspace/` 输入、`outputs/` 临时产物，以及 `published/` 资产仓或 submodule。

核心边界很简单：业务 repo 里的 `workspace/portfolios/<portfolio-id>/` 是母品牌 metadata 与元素库，`workspace/products/<portfolio-id>/<brand-id>/brand.lock.yaml` 是产品品牌锁定层，代表稳定品牌风格和 provider/model/参数；`workspace/products/<portfolio-id>/<brand-id>/campaigns/*.campaign.yaml` 是内容层，只能引用锁定层里已经定义好的 `alias.style`，不能自带画风描述。下游应用代码不跑生成，只消费业务 repo 的 asset repo/submodule 里的 `manifest.json` 或 release artifact。

## 方法论依据

本仓库按 Design System / Design Token 的方式组织。`brand.lock.yaml` 是品牌视觉决策的 single source of truth；token 结构遵循 W3C Design Tokens Format Module 的 `$value` + `$type` 约定，并分为：

- `global`: 原始视觉决策，例如颜色、字体、风格片段、负向词、参考资产。
- `alias`: 语义层，组合并引用 `global`，例如 `alias.style.launch-hero`。

参考：https://www.designtokens.org/tr/drafts/format/

治理保持轻：改 token，升 `version`，跑 regression，人工评分，通过后发布。等真正出现多项目协作和风格漂移问题时再加重流程。

`brand.lock.yaml` 的版本不是全局版本，而是某个 portfolio/product 命名空间下的锁定层版本。一次生成锁定的是这个 tuple：

```text
portfolio.id + portfolio.version + brand.id + brand.lock version + campaign + run
```

最小结构：

```yaml
portfolio:
  id: "codefox"
  name: "CodeFox"
  version: "1.0.0"
brand:
  id: "codefox"
  name: "CodeFox"
version: "1.1.0"
```

因此多个品牌都可以有 `1.1.0`，不会互相冲突；发布到 repo 快照时会按 `published/products/<portfolio-id>/<brand-id>/<brand-version>/...` 分开。portfolio 升版不自动重写产品品牌，产品需要显式 rebase 到新的 portfolio metadata 后才 bump 自己的 `brand.lock`。

版本职责分开：

- `portfolio.version`: 母品牌 metadata / 元素库规范版本。
- `brand.lock version`: 某个产品品牌的锁定风格/provider/model/params 版本。
- `campaign`: 一次具体宣发内容，不代表版本。
- `run`: 一次实际生成执行，记录在 `run.lock.json`。
- `accepted.revision`: 被人工接受的作品集合版本，只作为 proposal 输入，不隐式改变 render。

## 快速开始

开发这个 harness repo 自身时：

```bash
uv sync
cp skills/marketing-harness/.env.example .env
uv run harness validate skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml
uv run harness render skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml \
  --dry-run
```

标准入口是 `uv run harness`。如果某台机器暂时没有 `uv`，但仓库已经存在 `.venv/bin/harness`，可以临时用 `.venv/bin/harness ...` 跑同样的命令；长期仍建议把 `uv` 安装到 PATH。

`--dry-run` 不调用生图 API，会写 SVG 占位图、`run.lock.json` 和 `manifest.json`。

在其他业务 repo 中使用全局安装的 skill 时，不需要复制 harness 源码。保持 cwd 在业务 repo，使用 skill 里的 launcher 运行 harness：

```bash
SKILL_ROOT="$HOME/.codex/skills/marketing-harness"  # Claude Code 中也可能是 $CLAUDE_SKILL_DIR
sh "$SKILL_ROOT/scripts/bootstrap_project.sh" .
python3 "$SKILL_ROOT/scripts/harness.py" validate workspace/products/<portfolio-id>/<brand-id>/campaigns/<name>.campaign.yaml \
  --brand workspace/products/<portfolio-id>/<brand-id>/brand.lock.yaml
python3 "$SKILL_ROOT/scripts/harness.py" render workspace/products/<portfolio-id>/<brand-id>/campaigns/<name>.campaign.yaml \
  --brand workspace/products/<portfolio-id>/<brand-id>/brand.lock.yaml \
  --dry-run
```

真生成时把 GPT Image skill/CLI 需要的凭证放在 `.env`：

```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
uv run harness render skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml
```

## Token 怎么改

在 `global` 加原始值：

```yaml
global:
  color:
    success-green: { $value: "#20A67A", $type: "color" }
```

在 `alias` 组合语义风格，只引用 `global`：

```yaml
alias:
  style:
    social-success:
      $type: "composite"
      $value:
        prompt: "{global.style-fragment.base-aesthetic}, optimistic launch composition"
        palette: ["{global.color.success-green}", "{global.color.bg-neutral}"]
        negative: "{global.negative.global-exclude}"
        references: []
```

campaign 只引用 alias，不写风格：

```yaml
style: "social-success"
content:
  headline: "Now Available"
  subject: "a clean product announcement visual"
```

## 风格生产

风格可以由 design skill 接管，但 design skill 的输出必须先冻结成 `brand.lock.yaml`。render 阶段不会动态询问 design skill。

推荐流程：

```bash
uv run harness style propose \
  --base workspace/products/codefox/codefox/brand.lock.yaml \
  --brief workspace/products/codefox/codefox/brief.md \
  --source workspace/products/codefox/codefox/references/ \
  --out workspace/products/codefox/codefox/proposals/codefox.lock.yaml \
  --version 1.2.0

uv run harness validate workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand workspace/products/codefox/codefox/proposals/codefox.lock.yaml

uv run harness regression \
  --brand workspace/products/codefox/codefox/proposals/codefox.lock.yaml \
  --dry-run
```

review 通过后再提升为正式 lock：

```bash
uv run harness style promote \
  workspace/products/codefox/codefox/proposals/codefox.lock.yaml \
  --to workspace/products/codefox/codefox/brand.lock.yaml
```

内置 `local` producer 是确定性的草案生成器，适合先打通流程。真正的 design skill 可以通过 `command` producer 接入：

```bash
uv run harness style propose \
  --producer command \
  --producer-command "./scripts/design-skill-producer" \
  --base workspace/products/codefox/codefox/brand.lock.yaml \
  --brief workspace/products/codefox/codefox/brief.md \
  --source workspace/products/codefox/codefox/references/ \
  --out workspace/products/codefox/codefox/proposals/codefox.lock.yaml
```

外部命令从 stdin 读取 JSON，向 stdout 写完整的 `brand.lock` YAML/JSON。harness 会继续用同一套 pydantic 和 token 引用规则校验输出。

## 生图入口

harness 现在只有一个 live 生图入口：本地 GPT Image skill/CLI。
`provider.gateway` 必须是 `gpt-image-skill`，或它的别名 `skill-cli`。
provider 会优先使用 `provider.params.command`，其次
`HARNESS_SKILL_CLI_COMMAND`，再找 PATH 上的 `gpt-image`，最后找
`~/.codex/skills/gpt-image/scripts/generate.py`。

```yaml
provider:
  gateway: "gpt-image-skill"
  model: "gpt-image-2"
  params:
    seed_strategy: "fixed"
    seed: 12345
    quality: "high"
    output_format: "png"
    command: "gpt-image"
```

`skill-cli` 会把 harness 组合出的最终 prompt 传给 CLI，并把 CLI 生成图本地裁切/缩放到 deliverable 的精确尺寸。若 alias style 有 reference assets，默认会以 `-i` 传给 CLI；缺失引用会报错，可用 `strict_references: false` 临时关闭。

改 model 或 params 属于锁定层变更，必须升 `version` 并跑 regression。

## 输出 Contract

每次 render 写到 `outputs/<campaign-name>/`：

- `<asset-id>.<ext>`: 每个规格的成品物料。
- `run.lock.json`: 本次 brand lock 快照、campaign、实际 seed/参数、时间戳、provider 元数据。
- `manifest.json`: 本地 render buffer 的 contract 草稿；发布后项目方消费 `published/products/<portfolio-id>/<brand-id>/<brand-version>/artifacts/<campaign>/manifest.json`。

manifest 最小消费示例：

```python
import json

manifest = json.load(open(
    "published/products/codefox/codefox/1.1.0/artifacts/feature-x-launch/manifest.json",
    encoding="utf-8",
))
hero = next(asset for asset in manifest["assets"] if asset["id"] == "web-banner")
print(hero["url"] or hero["path"])
```

`outputs/` 不提交、不作为项目方消费入口。完整生成流程是：render 成功后先人工验收图片、文字质量、尺寸和 brief 匹配度；验收通过后再执行 `harness publish <campaign> --channel repo --repo-dir published --publish`，把快照写入当前业务 repo 的 `published/` 资产仓或 submodule。API 成本确认不等于产物验收通过。

项目方应 pin `brand_lock_version` 或 release artifact 版本，不应直接运行生成。

## 输入来源演进

每个业务 repo 把“可编辑输入源”统一放在本地 `workspace/` 中：

```text
workspace/portfolios/<portfolio-id>/
├── portfolio.meta.yaml     母品牌 metadata
├── elements.yaml           母品牌元素库
└── accepted.yaml           母品牌已接受作品索引

workspace/products/<portfolio-id>/<brand-id>/
├── brand.lock.yaml         产品品牌 SSOT
├── brand.meta.yaml         当前产品 metadata
├── elements.yaml           当前产品元素库
├── accepted.yaml           当前产品已接受作品索引
├── campaigns/              campaign YAML
├── references/             参考资产，图片类走 Git LFS
└── proposals/              待 review 的 brand.lock proposal
```

`workspace/` 可以理解成 source buffer。这里的文件可 review、可 diff、可修改；发布时会把本次实际使用的输入复制到业务 repo 的 `published/products/<portfolio-id>/<brand-id>/<brand-version>/...` 作为不可变快照副本。

后续如果接多项目或远程素材库，不需要改变输出 contract，只需要在 `workspace` 前面加一层 source resolver，让输入既可以来自本地文件，也可以来自 URL / 对象存储 / registry：

```text
brand source       workspace/products/<portfolio-id>/<brand-id>/brand.lock.yaml | https://... | s3://... | brand://name@version
campaign source    workspace/products/<portfolio-id>/<brand-id>/campaigns/*.campaign.yaml | https://... | s3://...
reference source   workspace/products/<portfolio-id>/<brand-id>/references/* | https://... | s3://... | cdn://...
```

render 时先把远程 source resolve 到本地缓存或 workspace override，再走同一套校验和生成：

```text
local path / URL -> .harness/cache/... or workspace/... -> validate -> render -> outputs/ -> publish -> published/
```

到那时应 ignore resolver 拉下来的缓存和本地 override，而不是忽略整个 `workspace/`：

```gitignore
.harness/cache/
.harness/sources/
workspace/products/<portfolio-id>/<brand-id>/local/
workspace/products/<portfolio-id>/<brand-id>/campaigns/local/
workspace/products/<portfolio-id>/<brand-id>/references/local/
```

建议这个 harness repo 只保留 bundled example，例如 `skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml`、`skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml` 和少量参考资产；真实业务输入属于各业务 repo。这个演进只改变“输入从哪里读到 workspace/cache”，不改变风格锁定层、内容层、`outputs/` render buffer、`published/` 快照和 manifest contract 的边界。

## 发布

默认都是 dry-run：

```bash
uv run harness publish feature-x-launch --channel cdn
uv run harness publish feature-x-launch --channel release
uv run harness publish feature-x-launch --channel repo --repo-dir published
```

真正发布需要显式加 `--publish`：

```bash
uv run harness publish feature-x-launch --channel release --publish
uv run harness publish feature-x-launch --channel cdn --publish
uv run harness publish feature-x-launch --channel repo --repo-dir published --publish
```

live render 之后应先看 `outputs/<campaign>/` 里的图片、`manifest.json` 和 `run.lock.json`。只有用户或 reviewer 明确接受这次产物后，才把 `--publish` 当作最终发布动作。

CDN 通道使用 S3-compatible object storage，凭证只从环境变量读取，不写入配置或 manifest。release 通道会生成 `releases/<campaign>-brand-<version>.zip`，包含成品、`manifest.json` 和 `run.lock.json`。

repo 通道会把一次发布冻结成带 portfolio/product namespace 的仓库快照。这个快照推荐写入当前业务 repo 的 `published/` asset repo 或 git submodule；portfolio 快照也一起放在这个 asset repo 中。`version` 是某个 product brand 的 `brand.lock` 版本，不是全局版本，所以路径必须包含 `portfolio.id` 和 `brand.id`：

```text
published/portfolios/<portfolio-id>/<portfolio-version>/
├── portfolio.meta.yaml
├── elements.yaml
└── accepted.yaml

published/products/<portfolio-id>/<brand-id>/<brand-lock-version>/
├── portfolio/
│   ├── portfolio.meta.yaml
│   ├── elements.yaml
│   └── accepted.yaml
├── brand/
│   └── brand.lock.yaml
├── metadata/
│   ├── brand.meta.yaml
│   ├── elements.yaml
│   └── accepted.yaml
├── campaigns/
│   └── <campaign-name>.campaign.yaml
├── references/
│   └── <reference-assets>
└── artifacts/
    └── <campaign-name>/
        ├── <asset-id>.<ext>
        ├── manifest.json
        └── run.lock.json
```

目录可通过 `--repo-dir` 或 `HARNESS_REPO_PUBLISH_DIR` 改；默认是 `published`。repo 通道不会自动执行 `git add`、`commit` 或 `push`，你可以先检查快照，再在 asset repo/submodule 中提交，最后让业务 repo pin 对应 submodule commit。发布时会在 `published/.gitattributes` 写入图片 LFS 规则，避免大图直接膨胀 Git history。

## 回归流程

固定 prompt 集在 `tests/regression/prompts.yaml`。当 `brand.lock.yaml` 的 provider/model/params 或 token 变更时：

```bash
uv run harness regression
```

没有 API key 时可先跑占位：

```bash
uv run harness regression --dry-run
```

每次 regression 会输出对照图、`run.lock.json`、`manifest.json` 和 `scores.csv`。人工按 `scores.csv` 记录每条 prompt 的分数和备注；如果整体质量或关键 prompt 分数下降，不发布这次风格变更。这里不做伪自动判分，图像质量由人工评分把关。

## CI / Release

仓库提供三个 GitHub Actions workflow：

- `CI`: PR 和 `main` push 自动运行，执行 `ruff`、`pytest`、example campaign validate，以及 `render --dry-run`。它不调用生图 API，不需要 secrets。
- `Regression`: 手动触发，默认 dry-run；勾选 `live` 才调用 provider，并从 GitHub Secrets 读取当前 provider 需要的 key。
- `Release`: 手动触发，先 render 再 publish。默认 dry-run；勾选 `live_render` 才真实生图，勾选 `publish` 才执行发布动作。

需要配置的 GitHub Secrets / Variables：

```text
OPENAI_API_KEY
OPENAI_BASE_URL
HARNESS_SKILL_CLI_COMMAND   # optional local skill-cli command override
HARNESS_CDN_BUCKET
HARNESS_CDN_ENDPOINT
HARNESS_CDN_BASE_URL
HARNESS_CDN_ACCESS_KEY_ID
HARNESS_CDN_SECRET_ACCESS_KEY
HARNESS_CDN_PREFIX      # variable
HARNESS_CDN_REGION      # variable
HARNESS_REPO_PUBLISH_DIR # variable, defaults to published
```

## Agent Skill

本仓库是开发仓库；真正可安装的 skill payload 在
`skills/marketing-harness/`。它不是 Anthropic 官方维护的 official skill，但按
Claude Agent Skill 结构组织：`SKILL.md` 是入口，里面有 YAML frontmatter
（`name` 和 `description`）以及正文指令；旁边是 `scripts/`、`references/`、
`assets/` 和 `examples/`。

CLI 实现仍在仓库根目录：`src/`、`pyproject.toml` 和 `tests/`。skill 里有
`scripts/harness.py` launcher，会优先找本地 checkout / 已安装 CLI，找不到时
用 `uvx` 远端 fallback。

### Claude Code 使用

从 GitHub 安装 `marketing-harness` 这个子目录 skill：

```bash
npx skills add CodeFox-Repo/marketing-harness \
  --skill marketing-harness \
  --agent claude-code
```

如果工具询问安装哪个 skill，选择 `marketing-harness`。

### Codex 本地使用

Codex 从 `~/.codex/skills/` 发现本地 skill。本地使用时推荐软链到 skill 子目录：

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/marketing-harness" ~/.codex/skills/marketing-harness
```

如果软链已存在，先确认它指向本仓库：

```bash
readlink ~/.codex/skills/marketing-harness
```

这个软链只是本地安装方式，不是开发 wrapper，也不会在本仓库里创建第二份 skill。

在业务 repo 中使用时，skill 应从全局位置运行 harness launcher，但所有相对路径都落在当前业务 repo：

```bash
python3 "$SKILL_ROOT/scripts/harness.py" ...
```

launcher 会按顺序使用 `HARNESS_PROJECT_DIR`、本地开发 checkout、PATH 上的
`harness` CLI，最后用 `uvx --from git+https://github.com/CodeFox-Repo/marketing-harness`
远端 fallback。业务 repo 只需要自己的 `workspace/` 和 `published/`。

重开 Codex 会话后，用 `/skills` 选择 `marketing-harness`，或在 prompt 里显式 mention：

```text
$marketing-harness 校验 example campaign
$marketing-harness 从零做品牌风格，优先用本地 frontend-design
$marketing-harness dry-run render workspace/products/codefox/codefox/campaigns/example.campaign.yaml
```

也可以使用自然语言点名：

```text
使用 marketing-harness skill，校验 example campaign
使用 marketing-harness skill，从零做品牌风格，优先用本地 frontend-design
使用 marketing-harness skill，dry-run render workspace/products/codefox/codefox/campaigns/example.campaign.yaml
```

注意：Codex 不会按 skill 名自动生成 bare slash command，所以 `/marketing-harness` 不是默认入口；`/` 菜单里的 skill 入口是 `/skills`。

如果确实想从 slash 菜单启动一个固定提示，可以额外创建 Codex custom prompt alias。custom prompts 已被 Codex 文档标记为 deprecated，但仍可用：

```bash
mkdir -p ~/.codex/prompts
cat > ~/.codex/prompts/marketing-harness.md <<'EOF'
---
description: Use the marketing-harness skill from this repository
argument-hint: [REQUEST]
---

Use $marketing-harness. $ARGUMENTS
EOF
```

重启 Codex 后从 slash 菜单使用 `/prompts:marketing-harness ...`。

### Design Skill 路由

style 生产阶段可以由 design skill 接管，但只负责生成/整理风格资产和 `brand.lock` proposal，不直接 render 或 publish。skill 后面的文字会作为模糊路由 hint：

- 用户指定本地 design skill 时优先使用指定项，例如 `frontend-design` 或 `claude-design`。
- 用户没指定时，优先找已安装的本地 brand/frontend/visual design skill。
- 找不到合适本地 design skill 时停止；不会自动下载、clone 或安装网络 fallback，除非用户明确要求安装。
- 如果用户已经提供 reviewed brief 和 references，可以跳过 design skill，直接运行 `harness style propose`。

### 打包分发

如果要打包上传到 claude.ai 或其他支持 Agent Skills 的环境：

```bash
python3 scripts/package_skill.py
```

会生成：

```text
../marketing-harness.zip
```

zip 只包含 `skills/marketing-harness/`：`SKILL.md`、launcher scripts、
references、assets 和 examples。它不包含根目录 `src/` 或 `tests/`；真实 runtime
由本地 checkout、已安装 CLI 或 `uvx` 远端 fallback 提供。

## CLI

```bash
harness validate <campaign.yaml>
harness render <campaign.yaml> [--dry-run]
harness publish <campaign-name> [--channel cdn|release|repo] [--repo-dir published] [--publish]
harness style propose --out <workspace/products/codefox/codefox/proposals/name.lock.yaml> [--brief workspace/products/codefox/codefox/brief.md] [--source workspace/products/codefox/codefox/references/]
harness style promote <proposal.lock.yaml> --to <workspace/products/<portfolio-id>/<brand-id>/brand.lock.yaml>
harness regression
```

## 安全和约束

- API key、对象存储凭证只读 `.env` / 环境变量，绝不写进配置、日志或 manifest。
- campaign schema `extra=forbid`，不能夹带 prompt、palette、negative、references 等风格字段。
- token 引用只允许 `{global.x.y}`；断链和循环引用会在加载时失败。
- 同一锁定配置、同一 campaign、同一 seed 策略会写入 `run.lock.json`，用于追溯和重出。
