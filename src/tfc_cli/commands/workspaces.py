"""Workspace commands: list, show, lock, unlock, list-access, add-access, remove-access."""

import click
from rich.console import Console
from rich.table import Table

from tfc_cli.cli import Context, output_json, pass_context
from tfc_cli.client import TFCError
from tfc_cli.models import TeamAccess, Workspace


@click.group()
def workspaces() -> None:
    """Manage workspaces."""


@workspaces.command("list")
@click.option("--search", default=None, help="Filter workspaces by name")
@pass_context
def ws_list(ctx: Context, search: str | None) -> None:
    """List workspaces in the organization."""
    client = ctx.client
    params: dict[str, str] = {}
    if search:
        params["search[name]"] = search

    raw_items = client.get_all(f"/organizations/{client.org}/workspaces", params=params)

    if ctx.json_output:
        output_json(raw_items)
        return

    items = [Workspace.model_validate(item) for item in raw_items]
    console = Console()
    table = Table(title=f"Workspaces — {client.org}")
    table.add_column("Name", style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("Terraform Version")
    table.add_column("Locked", justify="center")
    table.add_column("Updated At")

    for ws in items:
        table.add_row(
            ws.attributes.name,
            ws.id,
            ws.attributes.terraform_version or "—",
            "yes" if ws.attributes.locked else "",
            (ws.attributes.updated_at or "—")[:19],
        )

    console.print(table)


@workspaces.command("show")
@click.argument("name")
@pass_context
def ws_show(ctx: Context, name: str) -> None:
    """Show workspace details."""
    client = ctx.client
    data = client.get(f"/organizations/{client.org}/workspaces/{name}")

    if ctx.json_output:
        output_json(data)
        return

    ws = Workspace.model_validate(data["data"])
    a = ws.attributes
    console = Console()
    console.print(f"[bold cyan]{a.name}[/] ({ws.id})")
    console.print(f"  Terraform Version: {a.terraform_version or '—'}")
    console.print(f"  Execution Mode:    {a.execution_mode or '—'}")
    console.print(f"  Auto Apply:        {a.auto_apply}")
    console.print(f"  Locked:            {a.locked}")
    vcs_id = a.vcs_repo.identifier if a.vcs_repo else "—"
    console.print(f"  VCS Repo:          {vcs_id or '—'}")
    console.print(f"  Working Directory: {a.working_directory or '—'}")
    console.print(f"  Created:           {(a.created_at or '—')[:19]}")
    console.print(f"  Updated:           {(a.updated_at or '—')[:19]}")
    console.print(f"  Resource Count:    {a.resource_count or '—'}")


@workspaces.command("lock")
@click.argument("name")
@click.option("--reason", default=None, help="Lock reason")
@pass_context
def ws_lock(ctx: Context, name: str, reason: str | None) -> None:
    """Lock a workspace."""
    client = ctx.client
    ws_id = client.workspace_id(name)
    payload: dict[str, str] | None = {"reason": reason} if reason else None
    data = client.post(f"/workspaces/{ws_id}/actions/lock", payload)

    if ctx.json_output:
        output_json(data)
        return

    click.echo(click.style(f"Locked workspace {name}", fg="green"))


@workspaces.command("unlock")
@click.argument("name")
@click.option("--force", is_flag=True, help="Force unlock (even if locked by another user)")
@pass_context
def ws_unlock(ctx: Context, name: str, force: bool) -> None:
    """Unlock a workspace."""
    client = ctx.client
    ws_id = client.workspace_id(name)
    action = "force-unlock" if force else "unlock"
    data = client.post(f"/workspaces/{ws_id}/actions/{action}")

    if ctx.json_output:
        output_json(data)
        return

    prefix = "Force-unlocked" if force else "Unlocked"
    click.echo(click.style(f"{prefix} workspace {name}", fg="green"))


@workspaces.command("set")
@click.argument("name")
@click.option("--key", "-k", required=True, help="Attribute name (e.g. global-remote-state)")
@click.option("--value", "-v", required=True, help="Attribute value")
@pass_context
def ws_set(ctx: Context, name: str, key: str, value: str) -> None:
    """Set a workspace attribute (e.g. --key global-remote-state --value true)."""
    # Coerce value to appropriate type
    parsed_value: str | bool | int
    if value.lower() in ("true", "false"):
        parsed_value = value.lower() == "true"
    elif value.isdigit():
        parsed_value = int(value)
    else:
        parsed_value = value

    client = ctx.client
    data = client.patch(
        f"/organizations/{client.org}/workspaces/{name}",
        {
            "data": {
                "type": "workspaces",
                "attributes": {key: parsed_value},
            }
        },
    )

    if ctx.json_output:
        output_json(data)
        return

    click.echo(click.style(f"Set {key}={parsed_value} on {name}", fg="green"))


@workspaces.command("list-access")
@click.argument("name")
@pass_context
def ws_list_access(ctx: Context, name: str) -> None:
    """List team access for a workspace."""
    client = ctx.client
    ws_id = client.workspace_id(name)
    data = client.get("/team-access", params={"filter[workspace][id]": ws_id})
    raw_items = data.get("data", [])

    if ctx.json_output:
        output_json(raw_items)
        return

    # Resolve team names
    team_ids = {
        item["relationships"]["team"]["data"]["id"]
        for item in raw_items
        if item.get("relationships", {}).get("team", {}).get("data")
    }
    team_names: dict[str, str] = {}
    for tid in team_ids:
        try:
            resp = client.get(f"/teams/{tid}")
            team_names[tid] = resp["data"]["attributes"]["name"]
        except TFCError:
            team_names[tid] = tid

    items = [TeamAccess.model_validate(item) for item in raw_items]
    console = Console()
    table = Table(title=f"Team Access — {name}")
    table.add_column("Team", style="cyan")
    table.add_column("Access")
    table.add_column("Team Access ID", style="dim")
    table.add_column("Team ID", style="dim")

    for ta in items:
        team_id = ta.relationships.team.data.id if ta.relationships.team.data else "—"
        table.add_row(
            team_names.get(team_id, team_id),
            ta.attributes.access,
            ta.id,
            team_id,
        )

    console.print(table)


@workspaces.command("add-access")
@click.argument("name")
@click.argument("team_name")
@click.option(
    "--access",
    type=click.Choice(["read", "plan", "write", "admin", "custom"]),
    default="write",
    help="Access level (default: write)",
)
@pass_context
def ws_add_access(ctx: Context, name: str, team_name: str, access: str) -> None:
    """Grant a team access to a workspace."""
    client = ctx.client
    ws_id = client.workspace_id(name)

    # Resolve team name to ID
    raw_teams = client.get_all(f"/organizations/{client.org}/teams")
    team_id = None
    for team in raw_teams:
        if team["attributes"]["name"] == team_name:
            team_id = team["id"]
            break

    if not team_id:
        raise TFCError(f"Team '{team_name}' not found")

    payload = {
        "data": {
            "type": "team-access",
            "attributes": {"access": access},
            "relationships": {
                "workspace": {"data": {"id": ws_id, "type": "workspaces"}},
                "team": {"data": {"id": team_id, "type": "teams"}},
            },
        }
    }
    data = client.post("/team-access", payload)

    if ctx.json_output:
        output_json(data)
        return

    click.echo(click.style(f"Granted {team_name} {access} access to {name}", fg="green"))


@workspaces.command("remove-access")
@click.argument("team_access_id")
@pass_context
def ws_remove_access(ctx: Context, team_access_id: str) -> None:
    """Remove a team access entry by its ID (tws-xxx)."""
    client = ctx.client
    client.delete(f"/team-access/{team_access_id}")
    click.echo(click.style(f"Removed team access {team_access_id}", fg="green"))
