"""Run commands: list, show, apply, discard, cancel, force-cancel."""

import click
from rich.console import Console
from rich.table import Table

from tfc_cli.cli import Context, output_json, pass_context
from tfc_cli.models import Plan, Run

STATUS_COLORS: dict[str, str] = {
    "applied": "green",
    "planned_and_finished": "green",
    "planned": "yellow",
    "planning": "yellow",
    "applying": "yellow",
    "pending": "blue",
    "queued": "blue",
    "errored": "red",
    "discarded": "dim",
    "canceled": "dim",
    "force_canceled": "dim",
}


@click.group()
def runs() -> None:
    """Manage runs."""


@runs.command("list")
@click.argument("workspace")
@click.option("--status", default=None, help="Filter by status")
@click.option("--limit", default=20, help="Number of runs to show")
@pass_context
def runs_list(ctx: Context, workspace: str, status: str | None, limit: int) -> None:
    """List runs for a workspace."""
    client = ctx.client
    ws_id = client.workspace_id(workspace)
    params: dict[str, str] = {}
    if status:
        params["filter[status]"] = status

    raw_items = client.get_all(f"/workspaces/{ws_id}/runs", params=params, limit=limit)

    if ctx.json_output:
        output_json(raw_items)
        return

    items = [Run.model_validate(item) for item in raw_items]
    console = Console()
    table = Table(title=f"Runs — {workspace}")
    table.add_column("Run ID", style="cyan")
    table.add_column("Status")
    table.add_column("Message", max_width=50)
    table.add_column("Created At")

    for run in items:
        color = STATUS_COLORS.get(run.attributes.status, "white")
        table.add_row(
            run.id,
            f"[{color}]{run.attributes.status}[/{color}]",
            (run.attributes.message or "—")[:50],
            (run.attributes.created_at or "—")[:19],
        )

    console.print(table)


@runs.command("show")
@click.argument("run_id")
@pass_context
def runs_show(ctx: Context, run_id: str) -> None:
    """Show run details."""
    client = ctx.client
    data = client.get(f"/runs/{run_id}")

    if ctx.json_output:
        output_json(data)
        return

    run = Run.model_validate(data["data"])
    a = run.attributes
    color = STATUS_COLORS.get(a.status, "white")
    console = Console()

    console.print(f"[bold cyan]{run.id}[/]")
    console.print(f"  Status:       [{color}]{a.status}[/{color}]")
    console.print(f"  Message:      {a.message or '—'}")
    console.print(f"  Source:       {a.source or '—'}")
    console.print(f"  Trigger:      {a.trigger_reason or '—'}")
    console.print(f"  Auto Apply:   {a.auto_apply}")
    console.print(f"  Is Destroy:   {a.is_destroy}")
    console.print(f"  Created:      {(a.created_at or '—')[:19]}")

    actions = a.actions
    if actions.is_confirmable or actions.is_discardable or actions.is_cancelable:
        parts: list[str] = []
        if actions.is_confirmable:
            parts.append("[green]apply[/green]")
        if actions.is_discardable:
            parts.append("[yellow]discard[/yellow]")
        if actions.is_cancelable:
            parts.append("[red]cancel[/red]")
        console.print(f"  Actions:      {', '.join(parts)}")

    # Show plan summary if available
    plan_rel = run.relationships.plan.data
    if plan_rel:
        plan_data = client.get(f"/plans/{plan_rel.id}")
        plan = Plan.model_validate(plan_data["data"])
        p = plan.attributes
        console.print(
            f"  Plan Summary: [green]+{p.resource_additions}[/green] "
            f"[yellow]~{p.resource_changes}[/yellow] "
            f"[red]-{p.resource_destructions}[/red]"
        )


@runs.command("apply")
@click.argument("run_id")
@click.option("--comment", default=None, help="Apply comment")
@click.option("--auto-approve", is_flag=True, help="Skip confirmation prompt")
@pass_context
def runs_apply(ctx: Context, run_id: str, comment: str | None, auto_approve: bool) -> None:
    """Apply a run (confirm a plan)."""
    if not auto_approve:
        click.confirm(f"Apply run {run_id}?", abort=True)

    client = ctx.client
    payload: dict[str, str] | None = {"comment": comment} if comment else None
    client.post(f"/runs/{run_id}/actions/apply", payload)
    click.echo(click.style(f"Applied run {run_id}", fg="green"))


@runs.command("discard")
@click.argument("run_id")
@click.option("--comment", default=None, help="Discard comment")
@pass_context
def runs_discard(ctx: Context, run_id: str, comment: str | None) -> None:
    """Discard a run."""
    client = ctx.client
    payload: dict[str, str] | None = {"comment": comment} if comment else None
    client.post(f"/runs/{run_id}/actions/discard", payload)
    click.echo(click.style(f"Discarded run {run_id}", fg="yellow"))


@runs.command("cancel")
@click.argument("run_id")
@click.option("--comment", default=None, help="Cancel comment")
@pass_context
def runs_cancel(ctx: Context, run_id: str, comment: str | None) -> None:
    """Cancel a run."""
    client = ctx.client
    payload: dict[str, str] | None = {"comment": comment} if comment else None
    client.post(f"/runs/{run_id}/actions/cancel", payload)
    click.echo(click.style(f"Cancelled run {run_id}", fg="yellow"))


@runs.command("force-cancel")
@click.argument("run_id")
@click.option("--comment", default=None, help="Cancel comment")
@pass_context
def runs_force_cancel(ctx: Context, run_id: str, comment: str | None) -> None:
    """Force-cancel a run."""
    click.confirm(f"Force-cancel run {run_id}? This cannot be undone.", abort=True)

    client = ctx.client
    payload: dict[str, str] | None = {"comment": comment} if comment else None
    client.post(f"/runs/{run_id}/actions/force-cancel", payload)
    click.echo(click.style(f"Force-cancelled run {run_id}", fg="red"))
