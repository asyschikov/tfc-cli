"""Organization commands: list, show."""

import click
from rich.console import Console
from rich.table import Table

from tfc_cli.cli import Context, output_json, pass_context
from tfc_cli.models import Organization


@click.group()
def orgs() -> None:
    """Manage organizations."""


@orgs.command("list")
@pass_context
def orgs_list(ctx: Context) -> None:
    """List organizations you have access to."""
    client = ctx.client
    raw_items = client.get_all("/organizations")

    if ctx.json_output:
        output_json(raw_items)
        return

    items = [Organization.model_validate(item) for item in raw_items]
    console = Console()
    table = Table(title="Organizations")
    table.add_column("Name", style="cyan")
    table.add_column("Email")
    table.add_column("Plan")
    table.add_column("Created At")

    for org in items:
        a = org.attributes
        table.add_row(
            a.name,
            a.email or "—",
            a.plan or "—",
            (a.created_at or "—")[:19],
        )

    console.print(table)


@orgs.command("show")
@click.argument("name", required=False)
@pass_context
def orgs_show(ctx: Context, name: str | None) -> None:
    """Show organization details. Defaults to current org."""
    client = ctx.client
    org_name = name or client.org
    data = client.get(f"/organizations/{org_name}")

    if ctx.json_output:
        output_json(data)
        return

    org = Organization.model_validate(data["data"])
    a = org.attributes
    console = Console()

    console.print(f"[bold cyan]{a.name}[/] ({org.id})")
    console.print(f"  Email:             {a.email or '—'}")
    console.print(f"  Plan:              {a.plan or '—'}")
    console.print(f"  Cost Estimation:   {a.cost_estimation_enabled}")
    console.print(f"  Sentinel:          {a.sentinel_enabled}")
    console.print(f"  Run Task Limits:   {a.run_task_limit or '—'}")
    console.print(f"  Created:           {(a.created_at or '—')[:19]}")
