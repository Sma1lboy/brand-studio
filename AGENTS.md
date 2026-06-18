# Agent Instructions

## GitHub Workflow

Do not use Codex-native or agent-native commit/PR automation for this repository.
In particular, do not use any tool path that creates commits or pull requests
with an automatic `[codex]` title prefix.

Use ordinary repository tools instead:

- inspect changes with `git status`, `git diff`, and `git log`
- commit with `git add` and `git commit`
- push with `git push`
- open or update pull requests with `gh pr create`, `gh pr edit`, and
  `gh pr view`

PR titles should describe the change directly and should not include `[codex]`
unless the user explicitly asks for that prefix.

Before committing or opening a PR, inspect the working tree and stage only the
files that belong to the requested change. Never commit secrets, `.env`, local
outputs, or unrelated user changes.
