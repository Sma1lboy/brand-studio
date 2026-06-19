# Marketing Harness Skill

[English](README.md)

Marketing Harness 是一个可安装的 agent skill，用来规划和沉淀“主题风格锁定”的宣发资产。安装一次后，在任意业务 repo 里唤起它；agent 会校验视觉 token、准备 campaign、导出给第三方素材生产 skill 使用的 dry-run 上下文，并只把人工验收过的资产沉淀到当前业务 repo 的视觉资产状态里。

这个 repo 交付一个可安装 skill payload 和维护工具：

- `skills/marketing-harness/`: 真正可安装的 skill payload。
- `scripts/package_skill.py`: 只打包 skill payload。

agent 使用的 runtime 在 `skills/marketing-harness/scripts/` 里。skill 形态不应该有根级 `src/` package。

## 推荐分享方式

个人或团队真实使用时，推荐 fork 这个仓库，再 clone 或 install 自己的 fork。
`CodeFox-Repo/marketing-harness` 只作为通用 upstream；`your-user/marketing-harness`
或 `your-org/marketing-harness` 才是你们同步 metadata、policy、producer 偏好、
模板和安装说明的 source of truth。

业务 repo 应该通过 submodule、tag 或本地安装 pin 到这个 fork。具体产品自己的
`theme.md`、campaign、accepted state、public assets 仍然放在业务 repo 或资产
repo 里；跨成员、跨 repo 共享的默认行为放在 fork 里，团队成员 pull 同一个 skill
行为。

## 这个 Skill 做什么

Marketing Harness 强制把“风格”和“内容”分开：

```text
repo visual state -> production plan -> candidates -> user acceptance -> accepted state -> next production
```

skill 会帮助 agent 完成这些事：

- 读取小型 YAML/JSON metadata，明确业务 repo 的路径和策略。
- 在 planning 前读取组织、当前 repo、相关 repo 和目录级资产状态。
- 构建或更新 theme notes 和 design-token 风格锁。
- 校验 `theme.md` frontmatter 和 campaign YAML。
- 先跑不花 API 钱的 dry-run。
- 把 dry-run 上下文交给用户选择的第三方素材生产 skill。
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
$marketing-harness 为这个 repo 初始化一个新产品视觉系统
$marketing-harness 校验 CodeFox example campaign
$marketing-harness 为 Claude 做一张 flag poster campaign，先 dry-run
$marketing-harness 用当前 theme 真实出图，然后等我验收
$marketing-harness 把已接受的 launch banner 沉淀到视觉资产状态
```

安装后的 skill 内置一个 launcher：

```bash
python3 "$SKILL_ROOT/scripts/harness.py" ...
```

launcher 会让所有相对路径仍然落在当前业务 repo，并运行当前 skill 内置的脚本。它不会调用 `uvx`，也不会向上寻找父级 runtime checkout。

## 业务 Repo 目录

业务 repo 拥有输入和产物。路径应该来自 metadata，而不是写死根目录结构。常见形态可以是：

```text
assets/marketing/
  theme.md
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
.harness/marketing/out/
```

- `project.marketingRoot`: 可编辑输入，包括 theme notes、风格锁、campaign YAML、proposal、references 和 accepted work 记录。
- `artifacts.scratch`: 本地 render buffer。
- `artifacts.approved`: 人工验收后的资产目录、资产仓路径或 submodule 目标。
- `state.assetIndex`: 当前 repo 的视觉资产记忆。
- `state.accepted`: 未来 planning 会读取的 durable accepted corpus。
- `state.directoryStateFile`: 每个目录下的状态文件名，通常是
  `asset-state.yaml`。
- `sources.relatedRepos`: 同 org 的相关产品 repo，读取它们的 accepted state
  来影响当前 repo 的生产。

raw scratch outputs 默认没有长期价值；只有人工验收后的最终资产才应该进入 approved 路径和 accepted state。

生产 banner、landscape visual、slide/PPT background、logo theme variant、
X/XHS 宣传图或社媒图之前，agent 应先跑只读 state preflight，并把结果写进
production plan：

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --metadata path/to/marketing.harness.yaml state
```

第三方素材生产 skill 按 metadata resolve 出来的本地 capability 管理，不作为
Marketing Harness 自己 vendored 的依赖。org rules metadata 可以维护 allowlisted
`skillRegistry` 和 declarative install hint；业务 repo metadata 用 `skills` 把本地
key 绑定到 registry id；campaign 用 `requires.skills` 声明本次需要哪些 capability。
生产环境推荐把 org rules repo 作为业务 repo 的 submodule 接入，例如
`vendor/marketing-rules`，然后让 `sources.skillRegistries` 指到
`vendor/marketing-rules/skills.yaml`。agent 不能自动安装、静默切换 producer，也不能在
generation 时拉取 remote rules。真实出图前先跑只读 resolver：

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --metadata path/to/marketing.harness.yaml skills
```

## Theme Contract

`theme.md` 是当前 repo 视觉方向的 single source of truth。YAML frontmatter
存机器可读的 style tokens 和 producer hints，Markdown 正文写给人和 agent
看的设计理念。token 结构遵循 W3C Design Tokens Format Module 的 `$value` +
`$type` 约定。

参考：https://www.designtokens.org/tr/drafts/format/

锁定层分两层：

- `global`: 原始视觉决策，例如颜色、字体、风格片段、负向词和参考资产。
- `alias`: 语义风格配方，引用 `global`，例如 `alias.style.launch-hero`。

campaign 只能选择已经锁定的 style alias，并填写这次的内容：headline、subject、deliverable size。campaign 不能内联 prompt、palette、negative prompt、reference image、model 或 producer params。`theme.md` frontmatter 里的 `producer.model` 是可选提示；是否使用由外部 producer skill 决定。

## 人工验收

同意花 API 钱出图，不等于同意发布产物。

skill 应先 dry-run；真实调用 API 前确认成本和所选 producer；生成后展示文件给用户检查。只有用户或 reviewer 明确接受具体文件或 asset id 后，才更新 accepted state。

修改官方 theme 或沉淀 live assets 前，用 dry-run render 做人工复核。harness 不假装自动判断图片质量，也不提供用户手动添加资产的命令界面。

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

真实素材生成由外部 producer skill 负责。Marketing Harness 不保存 API key，
也不包装 OpenAI/Gemini/其他图像 API。凭证只应该存在于所选 producer 的环境
或配置里，不应写进 YAML、manifest、run lock、日志或 accepted 快照。

## 维护者说明

repo 根目录用于维护 skill：

```bash
uv sync
uv run ruff check .
uv run pytest
cd skills/marketing-harness/examples/codefox
python3 ../../scripts/harness.py --metadata marketing.harness.yaml validate
```

只打包 skill payload：

```bash
python3 scripts/package_skill.py
```

zip 只包含 `skills/marketing-harness/` 内容。它不会打包根目录的 `tests/`、`examples/`、`outputs/` 或 `published/`。只有维护/debug 包才使用 `--include-examples`。

skill payload 形态靠人工 review 维护：保持 `SKILL.md`、`scripts/`、
`references/`、`assets/` 和 `agents/` 为主。打包脚本只负责生成 artifact 和默认
排除维护目录。
