# Contributing

## Requirements

- **Python 3.14+** — we use modern syntax (PEP 604 unions, PEP 649 deferred annotations, PEP 758 bare except tuples). No `from __future__ import annotations` needed.
- **uv** for dependency/project management

## Project structure

```
tfc-cli/
├── pyproject.toml              # Dependencies, entry point, ruff config
├── bin/tfc                     # Shell wrapper so `tfc` works from anywhere
├── src/tfc_cli/
│   ├── cli.py                  # Main click group, global options (--token, --org, --json)
│   ├── config.py               # Token and org resolution (CLI flag → env var → file)
│   ├── client.py               # TFC API client (auth, pagination, workspace resolution)
│   ├── models.py               # Pydantic models for all TFC API resources
│   └── commands/
│       ├── workspaces.py       # tfc workspaces {list,show,lock,unlock}
│       ├── runs.py             # tfc runs {list,show,apply,discard,cancel,force-cancel}
│       ├── plans.py            # tfc plans {show,log,json}
│       ├── state.py            # tfc state {current,list,download,outputs}
│       ├── variables.py        # tfc vars {list,set,delete}
│       └── orgs.py             # tfc orgs {list,show}
```

### Key modules

- **`cli.py`** — Defines the root `cli` click group with `--token`, `--org`, and `--json` global options. Creates a `Context` object holding the API client and output preferences. All command groups are registered at the bottom of this file.

- **`config.py`** — Resolves token (CLI flag → `TFC_TOKEN` env var → `.tfc-cli.json` local file → `~/.terraform.d/credentials.tfrc.json`) and org (CLI flag → `TFC_ORG` env var → `.tfc-cli.json` local file). The local file is written by `tfc config set-token` / `set-org`.

- **`client.py`** — `TFCClient` wraps httpx with TFC auth headers, error handling for common status codes (401/403/404/409/429), auto-pagination via `get_all()`, and workspace name-to-ID resolution with per-session caching.

- **`models.py`** — Pydantic models for TFC API resources. All models extend `TFCModel` which auto-generates kebab-case aliases from snake_case field names (matching the TFC JSON:API convention). Use `populate_by_name=True` so both `resource_count` and `resource-count` work.

- **`commands/*.py`** — Each file defines a click group with subcommands. Every command receives the shared `Context` via `@pass_context` and uses `ctx.client` for API calls. Commands support `--json` output by checking `ctx.json_output`. API responses are validated through pydantic models before rendering.

## Adding pydantic models

All models inherit from `TFCModel` which auto-converts field names to kebab-case aliases. Just write normal snake_case fields:

```python
from tfc_cli.models import TFCModel

class MyResourceAttributes(TFCModel):
    resource_name: str            # auto-aliases to "resource-name"
    created_at: str | None = None # auto-aliases to "created-at"
    is_active: bool = False       # auto-aliases to "is-active"

class MyResource(TFCModel):
    id: str
    attributes: MyResourceAttributes
```

Then validate API responses:

```python
data = client.get(f"/my-resources/{resource_id}")
resource = MyResource.model_validate(data["data"])
print(resource.attributes.resource_name)  # access via snake_case
```

## Adding a new command group

1. Add models to `models.py` (extend `TFCModel`)

2. Create `src/tfc_cli/commands/myresource.py`:

```python
import click
from rich.console import Console
from rich.table import Table

from tfc_cli.cli import Context, output_json, pass_context
from tfc_cli.models import MyResource


@click.group()
def myresource() -> None:
    """Manage my resources."""


@myresource.command("list")
@pass_context
def myresource_list(ctx: Context) -> None:
    """List resources."""
    client = ctx.client
    raw_items = client.get_all("/some/endpoint")

    if ctx.json_output:
        output_json(raw_items)
        return

    items = [MyResource.model_validate(item) for item in raw_items]
    console = Console()
    table = Table(title="My Resources")
    table.add_column("Name", style="cyan")
    for item in items:
        table.add_row(item.attributes.resource_name)
    console.print(table)
```

3. Register it in `cli.py`:

```python
from tfc_cli.commands.myresource import myresource  # noqa: E402
cli.add_command(myresource)
```

## Adding a subcommand to an existing group

Add a new function in the relevant `commands/*.py` file decorated with `@groupname.command("name")` and `@pass_context`. Follow the existing pattern: use `ctx.client` for API calls, validate with pydantic models, check `ctx.json_output` for JSON mode, and use `rich` tables for human-readable output.

## Development

```bash
# Install dependencies
uv sync

# Run the CLI
uv run tfc --help

# Lint
uv run ruff check src/

# Format
uv run ruff format src/
```

## API client usage

```python
client = ctx.client

# Single resource
data = client.get(f"/runs/{run_id}")

# Paginated list (returns all items, respects limit)
items = client.get_all(f"/workspaces/{ws_id}/runs", params={...}, limit=20)

# Workspace name → ID (cached)
ws_id = client.workspace_id("my-workspace")

# Mutating operations
client.post(f"/runs/{run_id}/actions/apply", payload)
client.patch(f"/workspaces/{ws_id}/vars/{var_id}", payload)
client.delete(f"/workspaces/{ws_id}/vars/{var_id}")

# Raw downloads (archivist URLs for logs/state)
text = client.get_raw(url)
```
