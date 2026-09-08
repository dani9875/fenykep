# Claude Code — isolated devcontainer

This devcontainer runs Claude Code in its own container. It does not touch
your host machine's files, packages, or shell config.

## What it installs

- Ubuntu base image.
- Node.js 22. Claude Code needs this to install and run.
- Python 3.12. The Lithophane Shop backend (Lambda functions) needs this.
- Claude Code CLI (`@anthropic-ai/claude-code`), installed on container
  create.
- VS Code extensions: GitLens, Error Lens, Python.

## Prerequisites

Pick one:

**Option A — VS Code + Docker (local)**
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Install [VS Code](https://code.visualstudio.com/).
3. Install the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) in VS Code.

**Option B — GitHub Codespaces (no local install)**
1. Push your repo to GitHub.
2. Open the repo on github.com and click **Code → Codespaces → Create
   codespace**.

## Setup

1. Copy the `.devcontainer` folder into the root of your project repo.
2. Open the `devcontainer.json` file and check `workspaceFolder`. It
   currently points to `/workspaces/lithophane-shop`. Change the last
   path segment to match your actual repo folder name.
3. Open the repo in VS Code.
4. Run **Dev Containers: Reopen in Container** from the command palette
   (`Cmd/Ctrl+Shift+P`).
5. Wait for the build to finish. This takes a few minutes the first
   time.

## First run

1. Open a terminal inside the container (VS Code opens one automatically).
2. Run:
   ```
   claude
   ```
3. Follow the login prompt. It opens a browser window for you to sign
   in with your Anthropic account.
4. Once signed in, Claude Code has access to the files inside
   `/workspaces/lithophane-shop` — nothing outside the container.

## Excluding .git from Claude Code

Two files handle this, both go in your repo root alongside `.devcontainer/`:

- **`.claudeignore`** — same syntax as `.gitignore`. Contains `.git/`.
  This is Claude Code's own "don't pull this into context" file.
- **`.claude/settings.json`** — a `permissions.deny` rule for
  `Read(./.git/**)` as a second layer.

Both are included in this delivery — copy them into your repo root the
same way you copy `.devcontainer/`.

**Honest caveat:** as of recent Claude Code versions, both
`.claudeignore` and `permissions.deny` have documented cases where
they don't get enforced 100% of the time (tracked in Anthropic's own
GitHub issue tracker). For `.git` specifically this is low-stakes —
worst case Claude reads some binary git-internals noise, not a
secret — so the two files above are a reasonable, low-effort fix. If
you need a hard guarantee (e.g. because `.git` history contains
something sensitive), a `PreToolUse` hook that blocks the `Read` tool
for `.git/**` paths is the more reliable option; ask if you want that
set up instead.

## Notes

- Sign-in state does not persist between container rebuilds. Run
  `claude` again to sign back in after a rebuild.
- To add more VS Code extensions, add their IDs to the
  `customizations.vscode.extensions` array in `devcontainer.json`.
- To use a different Python or Node version, change the `version`
  field under the matching entry in `features`.