"""Apply commands: show, log."""

import click
import httpx
from rich.console import Console

from tfc_cli.cli import Context, output_json, pass_context
from tfc_cli.client import TFCClient, TFCError
from tfc_cli.models import Apply, Run


def _get_apply_id(client: TFCClient, run_id: str) -> str:
    """Get the apply ID from a run."""
    run_data = client.get(f"/runs/{run_id}")
    run = Run.model_validate(run_data["data"])
    apply_rel = run.relationships.apply.data
    if not apply_rel:
        raise TFCError("No apply found for this run")
    return apply_rel.id


@click.group()
def applies() -> None:
    """View apply details and logs."""


@applies.command("show")
@click.argument("run_id")
@pass_context
def applies_show(ctx: Context, run_id: str) -> None:
    """Show apply details for a run."""
    client = ctx.client
    apply_id = _get_apply_id(client, run_id)
    data = client.get(f"/applies/{apply_id}")

    if ctx.json_output:
        output_json(data)
        return

    apply = Apply.model_validate(data["data"])
    a = apply.attributes
    console = Console()

    console.print(f"[bold cyan]Apply for {run_id}[/] ({apply.id})")
    console.print(f"  Status:       {a.status or '—'}")
    console.print(
        f"  Resources:    "
        f"[green]+{a.resource_additions}[/green] "
        f"[yellow]~{a.resource_changes}[/yellow] "
        f"[red]-{a.resource_destructions}[/red] "
        f"[blue]↓{a.resource_imports}[/blue]"
    )


@applies.command("log")
@click.argument("run_id")
@pass_context
def applies_log(ctx: Context, run_id: str) -> None:
    """Stream apply log output for a run."""
    client = ctx.client
    apply_id = _get_apply_id(client, run_id)
    data = client.get(f"/applies/{apply_id}")
    apply = Apply.model_validate(data["data"])

    if not apply.attributes.log_read_url:
        raise TFCError("No log available for this apply")

    resp = httpx.get(apply.attributes.log_read_url, timeout=30.0)
    click.echo(resp.text)
