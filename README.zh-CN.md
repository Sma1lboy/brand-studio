# Marketing Harness Skill

[English](README.md)

Marketing Harness 是一个可安装的 agent skill，用来生产“品牌风格锁定”的宣发图片。安装一次后，在任意业务 repo 里唤起它；agent 会校验品牌 token、准备 campaign、通过本地 image skill/CLI 出图，并只把人工验收过的资产沉淀到当前业务 repo 的品牌状态里。

这个 repo 交付一个可安装 skill payload 和维护工具：

- `skills/marketing-harness/`: 真正可安装的 skill payload。
- `scripts/package_skill.py`: 只打包 skill payload。

agent 使用的 runtime 在 `skills/marketing-harness/scripts/` 里。skill 形态不应该有根级 `src/` package。

## 这个 Skill 做什么

Marketing Harness 强制把“风格”和“内容”分开：

```text
brand state -> production plan -> candidates -> user acceptance -> accepted state -> next production
```

skill 会帮助 agent 完成这些事：

- 读取小型 YAML/JSON metadata，明确业务 repo 的路径和策略。
- 在 planning 前读取组织、portfolio、当前 repo、相关 repo 和目录级资产状态。
- 构建或更新品牌 metadata 和 design-token 风格锁。
- 校验 `brand.lock.yaml` 和 campaign YAML。
- 先跑不花 API 钱的 dry-run。
- 通过本地 image skill/CLI 做真实出图。
- 在更新状态前要求人工验收产物。
- 把已接受文件复制到 approved assets，并更新 `accepted.yaml`。

下游应用只消费已接受文件和 manifest，不自己跑生成；scratch candidates 不是品牌记忆。

## 安装

Claude Code：

```bash
npx skills add CodeFox-Repo/marketing-harness \
  --skill marketing-harness \
  --agent claude-code
```

Codex 本地开发时，可以把 Codex 指到 skill 子目录：

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/marketing-harness" ~/.codex/skills/marketing-harness
```

安装后重启 agent。

## 使用

进入一个业务 repo，然后在任务里点名这个 skill：

```text
$marketing-harness 为这个 repo 初始化一个新产品品牌
$marketing-harness 校验 CodeFox example campaign
$marketing-harness 为 Claude 做一张 flag poster campaign，先 dry-run
$marketing-harness 用当前 brand lock 真实出图，然后等我验收
$marketing-harness 把已接受的 launch banner 沉淀到品牌状态
```

安装后的 skill 内置一个 launcher：

```bash
python3 "$SKILL_ROOT/scripts/harness.py" ...
```

launcher 会让所有相对路径仍然落在当前业务 repo，并运行当前 skill 内置的脚本。它不会调用 `uvx`，也不会向上寻找父级 runtime checkout。

## 业务 Repo 目录

业务 repo 拥有输入和产物。路径应该来自 metadata，而不是写死根目录结构。常见形态可以是：

```text
packages/branding/
  marketing/
    brand.lock.yaml
    campaigns/
    references/
    proposals/
    plans/
    asset-state.yaml
    accepted.yaml
  public/marketing/
    <channel-or-format>/
      asset-state.yaml
    <approved assets and manifests>
  .harness/out/
```

- `project.marketingRoot`: 可编辑输入，包括品牌 metadata、风格锁、campaign YAML、proposal、references 和 accepted work 记录。
- `artifacts.scratch`: 本地 render buffer。
- `artifacts.approved`: 人工验收后的资产目录、资产仓路径或 submodule 目标。
- `state.assetIndex`: 当前 repo 的视觉资产记忆。
- `state.accepted`: 未来 planning 会读取的 durable accepted corpus。
- `state.directoryStateFile`: 每个目录下的状态文件名，通常是
  `asset-state.yaml`。
- `sources.relatedRepos`: 同 org 或同 portfolio 的相关产品 repo，读取它们的
  accepted state 来影响当前 repo 的生产。

raw scratch outputs 默认没有长期价值；只有人工验收后的最终资产才应该进入 approved 路径和 accepted state。

生产 banner、landscape visual、slide/PPT background、logo theme variant、
X/XHS 宣传图或社媒图之前，agent 应先跑只读 state preflight，并把结果写进
production plan：

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --metadata path/to/marketing.harness.yaml state
```

## Brand Lock Contract

`brand.lock.yaml` 是某个产品品牌视觉风格的 single source of truth。token 结构遵循 W3C Design Tokens Format Module 的 `$value` + `$type` 约定。

参考：https://www.designtokens.org/tr/drafts/format/

锁定层分两层：

- `global`: 原始视觉决策，例如颜色、字体、风格片段、负向词和参考资产。
- `alias`: 语义风格配方，引用 `global`，例如 `alias.style.launch-hero`。

campaign 只能选择已经锁定的 style alias，并填写这次的内容：headline、subject、deliverable size。campaign 不能内联 prompt、palette、negative prompt、reference image、model 或 provider params。`brand.lock.yaml` 里的 `provider.model` 是可选项；不写时由底层 image CLI 使用自己的默认模型。

## 人工验收

同意花 API 钱出图，不等于同意发布产物。

skill 应先 dry-run；真实调用 API 前确认成本；live render 后展示生成文件给用户检查。只有用户或 reviewer 明确接受具体文件或 asset id 后，才更新 accepted state。

修改官方 brand lock 或沉淀 live assets 前，用 dry-run render 做人工复核。harness 不假装自动判断图片质量，也不提供用户手动添加资产的命令界面。

## Skill 内容

```text
skills/marketing-harness/
├── SKILL.md
├── agents/openai.yaml
├── scripts/
│   ├── harness.py
│   ├── cli.py
│   ├── harness_runtime/
│   ├── bootstrap_project.sh
│   └── check_harness.sh
├── references/
│   ├── contracts.md
│   └── workflows.md
├── assets/
```

`SKILL.md` 是 agent 加载后的操作手册；这份 README 是给人看的总览。详细 schema 和生命周期说明在 `references/` 里，agent 会按任务需要加载，避免每次把所有细节塞进上下文。

开发 checkout 可以带 `examples/`，但默认打包出来的 skill artifact 不包含 examples。

## Runtime 要求

dry-run 和校验：

- Python 3.9+
- 推荐安装 `uv`

真实出图：

- 本地 image skill/CLI，或用 `HARNESS_SKILL_CLI_COMMAND` 指向等价命令
- 通过环境变量提供所选 image provider 的凭证，例如：

```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
```

密钥只从环境读取，不应写进 YAML、manifest、run lock、日志或 accepted 快照。

## 维护者说明

repo 根目录用于维护 skill：

```bash
uv sync
uv run ruff check .
uv run pytest
python3 skills/marketing-harness/scripts/harness.py validate \
  skills/marketing-harness/examples/codefox/packages/branding/marketing/campaigns/example.campaign.yaml \
  --brand skills/marketing-harness/examples/codefox/packages/branding/marketing/brand.lock.yaml
```

只打包 skill payload：

```bash
python3 scripts/package_skill.py
```

zip 只包含 `skills/marketing-harness/` 内容。它不会打包根目录的 `tests/`、`examples/`、`outputs/` 或 `published/`。只有维护/debug 包才使用 `--include-examples`。

打包脚本会强制 skill payload 形态：顶层允许 `scripts/`、`references/`、`assets/` 和 `agents/`；如果 skill payload 顶层出现 `src/` 或 `tests/`，打包会失败。
