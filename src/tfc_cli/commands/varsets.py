"""Variable set commands: list, show, create, delete, add-project, remove-project."""

import click
from rich.console import Console
from rich.table import Table

from tfc_cli.cli import Context, output_json, pass_context
from tfc_cli.client import TFCError
from tfc_cli.models import Variable, VariableSet


@click.group("varsets")
def varsets() -> None:
    """Manage variable sets."""


@varsets.command("list")
@pass_context
def varsets_list(ctx: Context) -> None:
    """List variable sets in the organization."""
    client = ctx.client
    raw_items = client.get_all(f"/organizations/{client.org}/varsets")

    if ctx.json_output:
        output_json(raw_items)
        return

    items = [VariableSet.model_validate(item) for item in raw_items]
    console = Console()
    table = Table(title=f"Variable Sets — {client.org}")
    table.add_column("Name", style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("Global", justify="center")
    table.add_column("Vars", justify="right")
    table.add_column("Workspaces", justify="right")
    table.add_column("Projects", justify="right")

    for vs in items:
        a = vs.attributes
        table.add_row(
            a.name,
            vs.id,
            "yes" if a.is_global else "",
            str(a.var_count or 0),
            str(a.workspace_count or 0),
            str(a.project_count or 0),
        )

    console.print(table)


@varsets.command("show")
@click.argument("name")
@pass_context
def varsets_show(ctx: Context, name: str) -> None:
    """Show variable set details and its variables."""
    client = ctx.client
    varset = _find_varset_by_name(ctx, name)

    # Get variables in this varset
    raw_vars = client.get_all(f"/varsets/{varset.id}/relationships/vars")

    if ctx.json_output:
        output_json({"varset": varset.model_dump(by_alias=True), "vars": raw_vars})
        return

    a = varset.attributes
    console = Console()
    console.print(f"[bold cyan]{a.name}[/] ({varset.id})")
    console.print(f"  Description:  {a.description or '—'}")
    console.print(f"  Global:       {a.is_global}")
    console.print(f"  Priority:     {a.priority}")
    console.print(f"  Projects:     {a.project_count or 0}")
    console.print(f"  Workspaces:   {a.workspace_count or 0}")
    console.print()

    variables = [Variable.model_validate(v) for v in raw_vars]
    if variables:
        table = Table(title="Variables")
        table.add_column("Key", style="cyan")
        table.add_column("Value")
        table.add_column("Category")
        table.add_column("Sensitive", justify="center")
        for var in variables:
            va = var.attributes
            value = "(sensitive)" if va.sensitive else (va.value or "")
            if len(value) > 60:
                value = value[:57] + "..."
            table.add_row(va.key, value, va.category or "—", "yes" if va.sensitive else "")
        console.print(table)
    else:
        console.print("[dim]No variables.[/dim]")


@varsets.command("create")
@click.argument("name")
@click.option("--description", "-d", default=None, help="Description")
@click.option("--global", "is_global", is_flag=True, help="Apply to all workspaces")
@click.option("--priority", is_flag=True, help="Priority varset (overrides others)")
@pass_context
def varsets_create(ctx: Context, name: str, description: str | None, is_global: bool, priority: bool) -> None:
    """Create a variable set."""
    client = ctx.client
    attrs: dict = {"name": name, "global": is_global, "priority": priority}
    if description:
        attrs["description"] = description
    payload = {"data": {"type": "varsets", "attributes": attrs}}
    data = client.post(f"/organizations/{client.org}/varsets", payload)

    if ctx.json_output:
        output_json(data)
        return

    vs_id = data["data"]["id"]
    click.echo(click.style(f"Created variable set '{name}' ({vs_id})", fg="green"))


@varsets.command("delete")
@click.argument("name")
@pass_context
def varsets_delete(ctx: Context, name: str) -> None:
    """Delete a variable set."""
    varset = _find_varset_by_name(ctx, name)
    ctx.client.delete(f"/varsets/{varset.id}")
    click.echo(click.style(f"Deleted variable set '{name}'", fg="green"))


@varsets.command("add-project")
@click.argument("varset_name")
@click.argument("project_name")
@pass_context
def varsets_add_project(ctx: Context, varset_name: str, project_name: str) -> None:
    """Apply a variable set to a project."""
    client = ctx.client
    varset = _find_varset_by_name(ctx, varset_name)
    project_id = _find_project_id(ctx, project_name)

    payload = {"data": [{"type": "projects", "id": project_id}]}
    client.post(f"/varsets/{varset.id}/relationships/projects", payload)
    click.echo(click.style(f"Added varset '{varset_name}' to project '{project_name}'", fg="green"))


@varsets.command("remove-project")
@click.argument("varset_name")
@click.argument("project_name")
@pass_context
def varsets_remove_project(ctx: Context, varset_name: str, project_name: str) -> None:
    """Remove a variable set from a project."""
    client = ctx.client
    varset = _find_varset_by_name(ctx, varset_name)
    project_id = _find_project_id(ctx, project_name)

    payload = {"data": [{"type": "projects", "id": project_id}]}
    client.delete_with_body(f"/varsets/{varset.id}/relationships/projects", payload)
    click.echo(click.style(f"Removed varset '{varset_name}' from project '{project_name}'", fg="green"))


@varsets.command("add-var")
@click.argument("varset_name")
@click.argument("key")
@click.argument("value")
@click.option("--category", type=click.Choice(["terraform", "env"]), default="terraform", help="Variable category")
@click.option("--hcl", is_flag=True, help="Parse value as HCL")
@click.option("--sensitive", is_flag=True, help="Mark as sensitive")
@pass_context
def varsets_add_var(
    ctx: Context, varset_name: str, key: str, value: str, category: str, hcl: bool, sensitive: bool
) -> None:
    """Add or update a variable in a variable set."""
    client = ctx.client
    varset = _find_varset_by_name(ctx, varset_name)

    # Check if variable already exists
    raw_vars = client.get_all(f"/varsets/{varset.id}/relationships/vars")
    existing_id: str | None = None
    for raw_var in raw_vars:
        if raw_var["attributes"]["key"] == key:
            existing_id = raw_var["id"]
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

    if existing_id:
        data = client.patch(f"/varsets/{varset.id}/relationships/vars/{existing_id}", payload)
        action = "Updated"
    else:
        data = client.post(f"/varsets/{varset.id}/relationships/vars", payload)
        action = "Created"

    if ctx.json_output:
        output_json(data)
        return

    click.echo(click.style(f"{action} variable '{key}' in varset '{varset_name}'", fg="green"))


@varsets.command("remove-var")
@click.argument("varset_name")
@click.argument("key")
@pass_context
def varsets_remove_var(ctx: Context, varset_name: str, key: str) -> None:
    """Remove a variable from a variable set."""
    client = ctx.client
    varset = _find_varset_by_name(ctx, varset_name)

    raw_vars = client.get_all(f"/varsets/{varset.id}/relationships/vars")
    var_id: str | None = None
    for raw_var in raw_vars:
        if raw_var["attributes"]["key"] == key:
            var_id = raw_var["id"]
            break

    if not var_id:
        raise TFCError(f"Variable '{key}' not found in varset '{varset_name}'")

    client.delete(f"/varsets/{varset.id}/relationships/vars/{var_id}")
    click.echo(click.style(f"Removed variable '{key}' from varset '{varset_name}'", fg="green"))


def _find_varset_by_name(ctx: Context, name: str) -> VariableSet:
    """Find a variable set by name."""
    client = ctx.client
    raw_items = client.get_all(f"/organizations/{client.org}/varsets")
    for item in raw_items:
        if item["attributes"]["name"] == name:
            return VariableSet.model_validate(item)
    raise TFCError(f"Variable set '{name}' not found")


def _find_project_id(ctx: Context, name: str) -> str:
    """Find a project ID by name."""
    client = ctx.client
    raw_items = client.get_all(f"/organizations/{client.org}/projects")
    for item in raw_items:
        if item["attributes"]["name"] == name:
            return item["id"]
    raise TFCError(f"Project '{name}' not found")
