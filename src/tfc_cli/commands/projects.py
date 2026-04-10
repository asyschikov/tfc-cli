"""Project commands: list, show."""

import click
from rich.console import Console
from rich.table import Table

from tfc_cli.cli import Context, output_json, pass_context
from tfc_cli.client import TFCError
from tfc_cli.models import Project


@click.group()
def projects() -> None:
    """Manage projects."""


@projects.command("list")
@pass_context
def projects_list(ctx: Context) -> None:
    """List projects in the organization."""
    client = ctx.client
    raw_items = client.get_all(f"/organizations/{client.org}/projects")

    if ctx.json_output:
        output_json(raw_items)
        return

    items = [Project.model_validate(item) for item in raw_items]
    console = Console()
    table = Table(title=f"Projects — {client.org}")
    table.add_column("Name", style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("Workspaces", justify="right")
    table.add_column("Teams", justify="right")
    table.add_column("Created At")

    for proj in items:
        table.add_row(
            proj.attributes.name,
            proj.id,
            str(proj.attributes.workspace_count or "—"),
            str(proj.attributes.team_count or "—"),
            (proj.attributes.created_at or "—")[:19],
        )

    console.print(table)


@projects.command("show")
@click.argument("name")
@pass_context
def projects_show(ctx: Context, name: str) -> None:
    """Show project details by name."""
    client = ctx.client
    raw_items = client.get_all(f"/organizations/{client.org}/projects")
    project = None
    for item in raw_items:
        if item["attributes"]["name"] == name:
            project = Project.model_validate(item)
            break

    if not project:
        raise TFCError(f"Project '{name}' not found")

    if ctx.json_output:
        output_json(item)
        return

    attrs = project.attributes
    console = Console()
    console.print(f"[bold cyan]{attrs.name}[/] ({project.id})")
    console.print(f"  Workspaces:        {attrs.workspace_count or '—'}")
    console.print(f"  Teams:             {attrs.team_count or '—'}")
    console.print(f"  Execution Mode:    {attrs.default_execution_mode or '—'}")
    console.print(f"  Created:           {(attrs.created_at or '—')[:19]}")
    console.print()
    perms = attrs.permissions
    console.print("[bold]Permissions:[/]")
    for field in perms.model_fields:
        if getattr(perms, field):
            console.print(f"  {field.replace('_', '-')}")
