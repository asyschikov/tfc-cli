"""Team commands: list, show."""

import click
from rich.console import Console
from rich.table import Table

from tfc_cli.cli import Context, output_json, pass_context
from tfc_cli.client import TFCError
from tfc_cli.models import Team


@click.group()
def teams() -> None:
    """Manage teams."""


@teams.command("list")
@pass_context
def teams_list(ctx: Context) -> None:
    """List teams in the organization."""
    client = ctx.client
    raw_items = client.get_all(f"/organizations/{client.org}/teams")

    if ctx.json_output:
        output_json(raw_items)
        return

    items = [Team.model_validate(item) for item in raw_items]
    console = Console()
    table = Table(title=f"Teams — {client.org}")
    table.add_column("Name", style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("Members", justify="right")
    table.add_column("Visibility")

    for team in items:
        table.add_row(
            team.attributes.name,
            team.id,
            str(team.attributes.users_count or "—"),
            team.attributes.visibility or "—",
        )

    console.print(table)


@teams.command("show")
@click.argument("name")
@pass_context
def teams_show(ctx: Context, name: str) -> None:
    """Show team details by name."""
    client = ctx.client
    raw_items = client.get_all(f"/organizations/{client.org}/teams")
    team = None
    raw = None
    for item in raw_items:
        if item["attributes"]["name"] == name:
            team = Team.model_validate(item)
            raw = item
            break

    if not team:
        raise TFCError(f"Team '{name}' not found")

    if ctx.json_output:
        output_json(raw)
        return

    attrs = team.attributes
    console = Console()
    console.print(f"[bold cyan]{attrs.name}[/] ({team.id})")
    console.print(f"  Members:           {attrs.users_count or '—'}")
    console.print(f"  Visibility:        {attrs.visibility or '—'}")

    org_access = attrs.organization_access
    granted = [f.replace("_", "-") for f in org_access.model_fields if getattr(org_access, f)]
    if granted:
        console.print()
        console.print("[bold]Org Access:[/]")
        for perm in granted:
            console.print(f"  {perm}")
