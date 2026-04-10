"""State commands: current, list, download, outputs."""

import click
import httpx
from rich.console import Console
from rich.table import Table

from tfc_cli.cli import Context, output_json, pass_context
from tfc_cli.client import TFCError
from tfc_cli.models import StateVersion, StateVersionOutput


@click.group()
def state() -> None:
    """Manage workspace state."""


@state.command("current")
@click.argument("workspace")
@pass_context
def state_current(ctx: Context, workspace: str) -> None:
    """Show the current state version for a workspace."""
    client = ctx.client
    ws_id = client.workspace_id(workspace)
    data = client.get(f"/workspaces/{ws_id}/current-state-version")

    if ctx.json_output:
        output_json(data)
        return

    sv = StateVersion.model_validate(data["data"])
    a = sv.attributes
    console = Console()

    console.print(f"[bold cyan]Current State — {workspace}[/]")
    console.print(f"  State Version ID: {sv.id}")
    console.print(f"  Serial:           {a.serial or '—'}")
    console.print(f"  Terraform Version:{a.terraform_version or '—'}")
    console.print(f"  Resources:        {a.resources_processed or '—'}")
    console.print(f"  Created:          {(a.created_at or '—')[:19]}")
    console.print(f"  Size:             {a.size or '—'} bytes")


@state.command("list")
@click.argument("workspace")
@click.option("--limit", default=20, help="Number of state versions to show")
@pass_context
def state_list(ctx: Context, workspace: str, limit: int) -> None:
    """List state versions for a workspace."""
    client = ctx.client
    params: dict[str, str] = {
        "filter[workspace][name]": workspace,
        "filter[organization][name]": client.org,
    }
    raw_items = client.get_all("/state-versions", params=params, limit=limit)

    if ctx.json_output:
        output_json(raw_items)
        return

    items = [StateVersion.model_validate(item) for item in raw_items]
    console = Console()
    table = Table(title=f"State Versions — {workspace}")
    table.add_column("ID", style="cyan")
    table.add_column("Serial")
    table.add_column("TF Version")
    table.add_column("Resources")
    table.add_column("Created At")

    for sv in items:
        a = sv.attributes
        table.add_row(
            sv.id,
            str(a.serial or "—"),
            a.terraform_version or "—",
            str(a.resources_processed or "—"),
            (a.created_at or "—")[:19],
        )

    console.print(table)


@state.command("download")
@click.argument("workspace")
@click.option("--output", "output_file", default=None, help="Output file (default: stdout)")
@pass_context
def state_download(ctx: Context, workspace: str, output_file: str | None) -> None:
    """Download the current state file."""
    client = ctx.client
    ws_id = client.workspace_id(workspace)
    data = client.get(f"/workspaces/{ws_id}/current-state-version")
    sv = StateVersion.model_validate(data["data"])

    if not sv.attributes.hosted_state_download_url:
        raise TFCError("No state download URL available")

    resp = httpx.get(sv.attributes.hosted_state_download_url, timeout=30.0)
    state_content = resp.text

    if output_file:
        with open(output_file, "w") as f:
            f.write(state_content)
        click.echo(click.style(f"State written to {output_file}", fg="green"), err=True)
    else:
        click.echo(state_content)


@state.command("outputs")
@click.argument("workspace")
@pass_context
def state_outputs(ctx: Context, workspace: str) -> None:
    """Show outputs from the current workspace state."""
    client = ctx.client
    ws_id = client.workspace_id(workspace)
    data = client.get(f"/workspaces/{ws_id}/current-state-version", params={"include": "outputs"})

    if ctx.json_output:
        output_json(data)
        return

    included = data.get("included", [])
    outputs = [StateVersionOutput.model_validate(item) for item in included if item["type"] == "state-version-outputs"]

    if not outputs:
        click.echo("No outputs found.")
        return

    console = Console()
    table = Table(title=f"Outputs — {workspace}")
    table.add_column("Name", style="cyan")
    table.add_column("Value")
    table.add_column("Sensitive", justify="center")
    table.add_column("Type")

    for out in outputs:
        a = out.attributes
        value = "(sensitive)" if a.sensitive else str(a.value or "—")
        if len(value) > 80:
            value = value[:77] + "..."
        table.add_row(
            a.name or "—",
            value,
            "yes" if a.sensitive else "",
            a.type or "—" if not a.sensitive else "—",
        )

    console.print(table)
