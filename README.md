# tfc-cli

A CLI and MCP server for Terraform Cloud / HCP Terraform.

## Why this exists

HashiCorp ships the `terraform` binary for *local* workflows, but HCP Terraform (formerly Terraform Cloud) has no official command-line client. Everything happens through the web UI or raw API calls — there is no `tfc workspaces list`, no `tfc runs apply <id>`, no easy way to grep for a variable across workspaces from your terminal.

This project fills that gap. It wraps the TFC JSON:API in an ergonomic CLI, and exposes the same operations as an MCP server so agents (Claude Code, Claude Desktop, etc.) can drive Terraform Cloud directly.

## What it covers

- **Workspaces** — list, show, lock/unlock, set attributes, manage team access
- **Runs** — list, show, apply, discard, cancel, force-cancel
- **Plans** — fetch plan JSON (latest, pending, or by run id)
- **Applies** — show metadata, stream logs
- **State** — current state, history, download, read outputs
- **Variables** — list, set, delete workspace variables
- **Variable sets** — create, attach to projects, add/remove vars
- **Orgs, projects, teams** — list and show

## Install

Requires Python 3.14+ and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/asyschikov/tfc-cli.git
cd tfc-cli
uv sync
```

Put `bin/tfc` on your `$PATH` (or symlink it) for a global `tfc` command:

```bash
ln -s "$PWD/bin/tfc" ~/.local/bin/tfc
```

## Authentication

The fastest way to get set up is to save your token and default org to a local config file:

```bash
tfc config set-token <your-tfc-api-token>
tfc config set-org <your-org>
```

This writes to `.tfc-cli.json` at the project root (gitignored, `0600` permissions). You can see the exact path with `tfc config path`.

Token resolution order (first match wins):

1. `--token` flag
2. `TFC_TOKEN` environment variable
3. `.tfc-cli.json` local config file
4. `~/.terraform.d/credentials.tfrc.json` (written by `terraform login`)

Organization resolution order:

1. `--org` flag
2. `TFC_ORG` environment variable
3. `.tfc-cli.json` local config file

## Using it as a CLI

```bash
# See everything available
tfc help

# Workspaces
tfc workspaces list
tfc workspaces list --search prod
tfc workspaces show my-workspace
tfc workspaces lock my-workspace --reason "deploying"
tfc workspaces unlock my-workspace

# Runs
tfc runs list my-workspace --status planned
tfc runs show run-abc123
tfc runs apply run-abc123 --comment "lgtm"
tfc runs discard run-abc123

# Plans and applies
tfc plans get-latest my-workspace
tfc plans get run-abc123 --output-mode json
tfc applies log run-abc123

# State
tfc state current my-workspace
tfc state outputs my-workspace
tfc state download my-workspace -o state.json

# Variables
tfc vars list my-workspace
tfc vars set my-workspace AWS_REGION us-east-1 --category env
tfc vars delete my-workspace AWS_REGION

# JSON output for scripting
tfc --json workspaces list | jq '.[].attributes.name'
```

## Using it as an MCP server

The same operations are exposed through an MCP server (`tfc-mcp`), letting Claude Code or Claude Desktop drive Terraform Cloud directly.

### Claude Code

```bash
claude mcp add tfc -- uv run --project ~/projects/tfc-cli tfc-mcp
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tfc": {
      "command": "uv",
      "args": ["run", "--project", "/Users/you/projects/tfc-cli", "tfc-mcp"],
      "env": {
        "TFC_TOKEN": "your-token-here",
        "TFC_ORG": "your-org"
      }
    }
  }
}
```

The server reuses the same token/org resolution as the CLI, so if `TFC_TOKEN` is already in your environment you can omit the `env` block.

Once connected, the agent can call tools like `list_workspaces`, `show_run`, `apply_run`, `get_latest_plan`, `list_variables`, `set_variable`, etc. — the full command surface above.

## License

MIT — see [LICENSE](LICENSE).
