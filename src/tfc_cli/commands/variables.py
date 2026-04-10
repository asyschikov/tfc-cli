"""Variable commands: list, set, delete."""

import click
from rich.console import Console
from rich.table import Table

from tfc_cli.cli import Context, output_json, pass_context
from tfc_cli.client import TFCError
from tfc_cli.models import Variable


@click.group("vars")
def vars_group() -> None:
    """Manage workspace variables."""


@vars_group.command("list")
@click.argument("workspace")
@pass_context
def vars_list(ctx: Context, workspace: str) -> None:
    """List variables for a workspace."""
    client = ctx.client
    ws_id = client.workspace_id(workspace)
    data = client.get(f"/workspaces/{ws_id}/vars")
    raw_items: list[dict] = data.get("data", [])

    if ctx.json_output:
        output_json(raw_items)
        return

    items = [Variable.model_validate(item) for item in raw_items]
    console = Console()
    table = Table(title=f"Variables — {workspace}")
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_column("Category")
    table.add_column("HCL", justify="center")
    table.add_column("Sensitive", justify="center")

    for var in items:
        a = var.attributes
        value = "(sensitive)" if a.sensitive else (a.value or "")
        if len(value) > 60:
            value = value[:57] + "..."
        table.add_row(
            a.key,
            value,
            a.category or "—",
            "yes" if a.hcl else "",
            "yes" if a.sensitive else "",
        )

    console.print(table)


@vars_group.command("set")
@click.argument("workspace")
@click.argument("key")
@click.argument("value")
@click.option(
    "--category",
    type=click.Choice(["terraform", "env"]),
    default="terraform",
    help="Variable category",
)
@click.option("--hcl", is_flag=True, help="Parse value as HCL")
@click.option("--sensitive", is_flag=True, help="Mark as sensitive")
@pass_context
def vars_set(ctx: Context, workspace: str, key: str, value: str, category: str, hcl: bool, sensitive: bool) -> None:
    """Create or update a variable in a workspace."""
    client = ctx.client
    ws_id = client.workspace_id(workspace)

    # Check if variable already exists
    existing = client.get(f"/workspaces/{ws_id}/vars")
    existing_var: Variable | None = None
    for raw_var in existing.get("data", []):
        var = Variable.model_validate(raw_var)
        if var.attributes.key == key:
            existing_var = var
            break

    payload: dict = {
        "data": {
            "type": "vars",
            "attributes": {
                "key": key,
                "value": value,
                "category": category,
                "hcl": hcl,
                "sensitive": sensitive,
            },
        }
    }

    if existing_var:
        data = client.patch(f"/workspaces/{ws_id}/vars/{existing_var.id}", payload)
        action = "Updated"
    else:
        data = client.post(f"/workspaces/{ws_id}/vars", payload)
        action = "Created"

    if ctx.json_output:
        output_json(data)
        return

    click.echo(click.style(f"{action} variable {key} in {workspace}", fg="green"))


@vars_group.command("delete")
@click.argument("workspace")
@click.argument("key")
@pass_context
def vars_delete(ctx: Context, workspace: str, key: str) -> None:
    """Delete a variable from a workspace."""
    client = ctx.client
    ws_id = client.workspace_id(workspace)

    # Find the variable ID by key
    existing = client.get(f"/workspaces/{ws_id}/vars")
    var_id: str | None = None
    for raw_var in existing.get("data", []):
        var = Variable.model_validate(raw_var)
        if var.attributes.key == key:
            var_id = var.id
            break

    if not var_id:
        raise TFCError(f"Variable '{key}' not found in {workspace}")

    client.delete(f"/workspaces/{ws_id}/vars/{var_id}")
    click.echo(click.style(f"Deleted variable {key} from {workspace}", fg="green"))
