"""Plan commands: get, get-latest, get-pending."""

import json as json_mod

import click
import httpx
from rich.console import Console

from tfc_cli.cli import Context, output_json, pass_context
from tfc_cli.client import TFCClient, TFCError
from tfc_cli.models import Plan, Run

PENDING_STATUSES = ",".join(
    [
        "pending",
        "plan_queued",
        "planning",
        "planned",
        "cost_estimating",
        "cost_estimated",
        "policy_checking",
        "policy_checked",
        "policy_override",
    ]
)

OUTPUT_OPTION = click.option(
    "--output",
    "-o",
    "output_mode",
    type=click.Choice(["summary", "log", "json"]),
    default="summary",
    help="What to show: summary (default), log, or json",
)


def _get_plan(client: TFCClient, run_id: str) -> tuple[Run, Plan]:
    """Get the run and plan from a run ID."""
    run_data = client.get(f"/runs/{run_id}")
    run = Run.model_validate(run_data["data"])
    plan_rel = run.relationships.plan.data
    if not plan_rel:
        raise TFCError("No plan found for this run")
    plan_data = client.get(f"/plans/{plan_rel.id}")
    return run, Plan.model_validate(plan_data["data"])


def _render_plan(ctx: Context, client: TFCClient, run_id: str, output_mode: str) -> None:
    """Shared rendering logic for plan output modes."""
    if output_mode == "log":
        _, plan = _get_plan(client, run_id)
        if not plan.attributes.log_read_url:
            raise TFCError("No log available for this plan")
        resp = httpx.get(plan.attributes.log_read_url, timeout=30.0)
        click.echo(resp.text)

    elif output_mode == "json":
        _, plan = _get_plan(client, run_id)
        data = client.get(f"/plans/{plan.id}/json-output")
        click.echo(json_mod.dumps(data, indent=2))

    else:
        _, plan = _get_plan(client, run_id)

        if ctx.json_output:
            output_json(plan.model_dump(by_alias=True))
            return

        p = plan.attributes
        console = Console()
        console.print(f"[bold cyan]Plan for {run_id}[/] ({plan.id})")
        console.print(f"  Status:       {p.status or '—'}")
        console.print(f"  Has Changes:  {p.has_changes}")
        if p.resource_additions is not None:
            console.print(
                f"  Resources:    "
                f"[green]+{p.resource_additions}[/green] "
                f"[yellow]~{p.resource_changes}[/yellow] "
                f"[red]-{p.resource_destructions}[/red]"
            )
            console.print(
                f"  Outputs:      "
                f"[green]+{p.output_additions}[/green] "
                f"[yellow]~{p.output_changes}[/yellow] "
                f"[red]-{p.output_destructions}[/red]"
            )


@click.group()
def plans() -> None:
    """View plans."""


@plans.command("get")
@click.argument("run_id")
@OUTPUT_OPTION
@pass_context
def plans_get(ctx: Context, run_id: str, output_mode: str) -> None:
    """Get plan for a run."""
    _render_plan(ctx, ctx.client, run_id, output_mode)


@plans.command("get-latest")
@click.argument("workspace")
@OUTPUT_OPTION
@pass_context
def plans_get_latest(ctx: Context, workspace: str, output_mode: str) -> None:
    """Get the latest plan for a workspace."""
    client = ctx.client
    ws_id = client.workspace_id(workspace)
    raw_items = client.get_all(f"/workspaces/{ws_id}/runs", limit=1)

    if not raw_items:
        click.echo("No runs found for this workspace.")
        return

    run = Run.model_validate(raw_items[0])
    click.echo(click.style(f"Latest run: {run.id} ({run.attributes.status})", fg="cyan"), err=True)
    _render_plan(ctx, client, run.id, output_mode)


@plans.command("get-pending")
@click.argument("workspace")
@OUTPUT_OPTION
@pass_context
def plans_get_pending(ctx: Context, workspace: str, output_mode: str) -> None:
    """Get the latest pending plan for a workspace."""
    client = ctx.client
    ws_id = client.workspace_id(workspace)
    raw_items = client.get_all(
        f"/workspaces/{ws_id}/runs",
        params={"filter[status]": PENDING_STATUSES},
        limit=1,
    )

    if not raw_items:
        click.echo("No pending plans.")
        return

    run = Run.model_validate(raw_items[0])
    click.echo(click.style(f"Pending run: {run.id} ({run.attributes.status})", fg="cyan"), err=True)
    _render_plan(ctx, client, run.id, output_mode)
