"""MCP server exposing TFC CLI functionality as tools."""

import httpx
from mcp.server.fastmcp import FastMCP

from tfc_cli.client import TFCClient, TFCError
from tfc_cli.config import resolve_org, resolve_token
from tfc_cli.models import (
    Apply,
    Organization,
    Plan,
    Project,
    Run,
    StateVersion,
    StateVersionOutput,
    Team,
    Variable,
    VariableSet,
    Workspace,
)

mcp = FastMCP("tfc")

_client_instance: TFCClient | None = None


def _client() -> TFCClient:
    global _client_instance
    if _client_instance is None:
        token = resolve_token(None)
        org = resolve_org(None)
        _client_instance = TFCClient(token, org)
    return _client_instance


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


@mcp.tool()
def list_workspaces(search: str | None = None) -> list[dict]:
    """List workspaces in the organization. Optionally filter by name."""
    client = _client()
    params: dict[str, str] = {}
    if search:
        params["search[name]"] = search
    raw = client.get_all(f"/organizations/{client.org}/workspaces", params=params)
    return [Workspace.model_validate(i).model_dump(by_alias=True) for i in raw]


@mcp.tool()
def show_workspace(name: str) -> dict:
    """Show details for a workspace by name."""
    client = _client()
    data = client.get(f"/organizations/{client.org}/workspaces/{name}")
    return Workspace.model_validate(data["data"]).model_dump(by_alias=True)


@mcp.tool()
def lock_workspace(name: str, reason: str | None = None) -> str:
    """Lock a workspace. Optionally provide a reason."""
    client = _client()
    ws_id = client.workspace_id(name)
    payload: dict[str, str] | None = {"reason": reason} if reason else None
    client.post(f"/workspaces/{ws_id}/actions/lock", payload)
    return f"Locked workspace {name}"


@mcp.tool()
def unlock_workspace(name: str, force: bool = False) -> str:
    """Unlock a workspace. Use force=True to override another user's lock."""
    client = _client()
    ws_id = client.workspace_id(name)
    action = "force-unlock" if force else "unlock"
    client.post(f"/workspaces/{ws_id}/actions/{action}")
    prefix = "Force-unlocked" if force else "Unlocked"
    return f"{prefix} workspace {name}"


@mcp.tool()
def set_workspace_attribute(name: str, key: str, value: str) -> str:
    """Set a workspace attribute (e.g. key='global-remote-state', value='true')."""
    parsed: str | bool | int
    if value.lower() in ("true", "false"):
        parsed = value.lower() == "true"
    elif value.isdigit():
        parsed = int(value)
    else:
        parsed = value
    client = _client()
    client.patch(
        f"/organizations/{client.org}/workspaces/{name}",
        {"data": {"type": "workspaces", "attributes": {key: parsed}}},
    )
    return f"Set {key}={parsed} on {name}"


@mcp.tool()
def list_workspace_access(name: str) -> list[dict]:
    """List team access entries for a workspace."""
    client = _client()
    ws_id = client.workspace_id(name)
    data = client.get("/team-access", params={"filter[workspace][id]": ws_id})
    raw_items = data.get("data", [])

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

    result = []
    for item in raw_items:
        team_id = item.get("relationships", {}).get("team", {}).get("data", {}).get("id", "")
        result.append(
            {
                "id": item["id"],
                "access": item["attributes"]["access"],
                "team_id": team_id,
                "team_name": team_names.get(team_id, team_id),
            }
        )
    return result


@mcp.tool()
def add_workspace_access(name: str, team_name: str, access: str = "write") -> str:
    """Grant a team access to a workspace. Access: read, plan, write, admin, custom."""
    client = _client()
    ws_id = client.workspace_id(name)

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
    client.post("/team-access", payload)
    return f"Granted {team_name} {access} access to {name}"


@mcp.tool()
def remove_workspace_access(team_access_id: str) -> str:
    """Remove a team access entry by its ID (tws-xxx)."""
    client = _client()
    client.delete(f"/team-access/{team_access_id}")
    return f"Removed team access {team_access_id}"


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@mcp.tool()
def list_runs(workspace: str, status: str | None = None, limit: int = 20) -> list[dict]:
    """List runs for a workspace. Optionally filter by status."""
    client = _client()
    ws_id = client.workspace_id(workspace)
    params: dict[str, str] = {}
    if status:
        params["filter[status]"] = status
    raw = client.get_all(f"/workspaces/{ws_id}/runs", params=params, limit=limit)
    return [Run.model_validate(i).model_dump(by_alias=True) for i in raw]


@mcp.tool()
def show_run(run_id: str) -> dict:
    """Show details for a run, including plan summary."""
    client = _client()
    data = client.get(f"/runs/{run_id}")
    run = Run.model_validate(data["data"])
    result = run.model_dump(by_alias=True)

    plan_rel = run.relationships.plan.data
    if plan_rel:
        plan_data = client.get(f"/plans/{plan_rel.id}")
        plan = Plan.model_validate(plan_data["data"])
        result["plan_summary"] = plan.model_dump(by_alias=True)

    return result


@mcp.tool()
def apply_run(run_id: str, comment: str | None = None) -> str:
    """Apply a run (confirm a plan). This is a mutating action."""
    client = _client()
    payload: dict[str, str] | None = {"comment": comment} if comment else None
    client.post(f"/runs/{run_id}/actions/apply", payload)
    return f"Applied run {run_id}"


@mcp.tool()
def discard_run(run_id: str, comment: str | None = None) -> str:
    """Discard a run."""
    client = _client()
    payload: dict[str, str] | None = {"comment": comment} if comment else None
    client.post(f"/runs/{run_id}/actions/discard", payload)
    return f"Discarded run {run_id}"


@mcp.tool()
def cancel_run(run_id: str, comment: str | None = None) -> str:
    """Cancel a run."""
    client = _client()
    payload: dict[str, str] | None = {"comment": comment} if comment else None
    client.post(f"/runs/{run_id}/actions/cancel", payload)
    return f"Cancelled run {run_id}"


@mcp.tool()
def force_cancel_run(run_id: str, comment: str | None = None) -> str:
    """Force-cancel a run. This cannot be undone."""
    client = _client()
    payload: dict[str, str] | None = {"comment": comment} if comment else None
    client.post(f"/runs/{run_id}/actions/force-cancel", payload)
    return f"Force-cancelled run {run_id}"


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

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


def _get_plan(client: TFCClient, run_id: str) -> tuple[Run, Plan]:
    run_data = client.get(f"/runs/{run_id}")
    run = Run.model_validate(run_data["data"])
    plan_rel = run.relationships.plan.data
    if not plan_rel:
        raise TFCError("No plan found for this run")
    plan_data = client.get(f"/plans/{plan_rel.id}")
    return run, Plan.model_validate(plan_data["data"])


@mcp.tool()
def get_plan(run_id: str, include_log: bool = False) -> dict:
    """Get plan details for a run. Set include_log=True to include the full plan log."""
    client = _client()
    _, plan = _get_plan(client, run_id)
    result = plan.model_dump(by_alias=True)
    if include_log and plan.attributes.log_read_url:
        resp = httpx.get(plan.attributes.log_read_url, timeout=30.0)
        result["log"] = resp.text
    return result


@mcp.tool()
def get_latest_plan(workspace: str, include_log: bool = False) -> dict:
    """Get the latest plan for a workspace."""
    client = _client()
    ws_id = client.workspace_id(workspace)
    raw_items = client.get_all(f"/workspaces/{ws_id}/runs", limit=1)
    if not raw_items:
        return {"message": "No runs found for this workspace"}
    run = Run.model_validate(raw_items[0])
    _, plan = _get_plan(client, run.id)
    result = plan.model_dump(by_alias=True)
    result["run_id"] = run.id
    result["run_status"] = run.attributes.status
    if include_log and plan.attributes.log_read_url:
        resp = httpx.get(plan.attributes.log_read_url, timeout=30.0)
        result["log"] = resp.text
    return result


@mcp.tool()
def get_pending_plan(workspace: str, include_log: bool = False) -> dict:
    """Get the latest pending plan for a workspace."""
    client = _client()
    ws_id = client.workspace_id(workspace)
    raw_items = client.get_all(
        f"/workspaces/{ws_id}/runs",
        params={"filter[status]": PENDING_STATUSES},
        limit=1,
    )
    if not raw_items:
        return {"message": "No pending plans"}
    run = Run.model_validate(raw_items[0])
    _, plan = _get_plan(client, run.id)
    result = plan.model_dump(by_alias=True)
    result["run_id"] = run.id
    result["run_status"] = run.attributes.status
    if include_log and plan.attributes.log_read_url:
        resp = httpx.get(plan.attributes.log_read_url, timeout=30.0)
        result["log"] = resp.text
    return result


# ---------------------------------------------------------------------------
# Applies
# ---------------------------------------------------------------------------


def _get_apply_id(client: TFCClient, run_id: str) -> str:
    run_data = client.get(f"/runs/{run_id}")
    run = Run.model_validate(run_data["data"])
    apply_rel = run.relationships.apply.data
    if not apply_rel:
        raise TFCError("No apply found for this run")
    return apply_rel.id


@mcp.tool()
def show_apply(run_id: str) -> dict:
    """Show apply details for a run."""
    client = _client()
    apply_id = _get_apply_id(client, run_id)
    data = client.get(f"/applies/{apply_id}")
    return Apply.model_validate(data["data"]).model_dump(by_alias=True)


@mcp.tool()
def get_apply_log(run_id: str) -> str:
    """Get the apply log output for a run."""
    client = _client()
    apply_id = _get_apply_id(client, run_id)
    data = client.get(f"/applies/{apply_id}")
    apply = Apply.model_validate(data["data"])
    if not apply.attributes.log_read_url:
        raise TFCError("No log available for this apply")
    resp = httpx.get(apply.attributes.log_read_url, timeout=30.0)
    return resp.text


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@mcp.tool()
def get_current_state(workspace: str) -> dict:
    """Show the current state version for a workspace."""
    client = _client()
    ws_id = client.workspace_id(workspace)
    data = client.get(f"/workspaces/{ws_id}/current-state-version")
    return StateVersion.model_validate(data["data"]).model_dump(by_alias=True)


@mcp.tool()
def list_state_versions(workspace: str, limit: int = 20) -> list[dict]:
    """List state versions for a workspace."""
    client = _client()
    params: dict[str, str] = {
        "filter[workspace][name]": workspace,
        "filter[organization][name]": client.org,
    }
    raw = client.get_all("/state-versions", params=params, limit=limit)
    return [StateVersion.model_validate(i).model_dump(by_alias=True) for i in raw]


@mcp.tool()
def download_state(workspace: str) -> str:
    """Download the current state file as JSON text."""
    client = _client()
    ws_id = client.workspace_id(workspace)
    data = client.get(f"/workspaces/{ws_id}/current-state-version")
    sv = StateVersion.model_validate(data["data"])
    if not sv.attributes.hosted_state_download_url:
        raise TFCError("No state download URL available")
    resp = httpx.get(sv.attributes.hosted_state_download_url, timeout=30.0)
    return resp.text


@mcp.tool()
def get_state_outputs(workspace: str) -> list[dict]:
    """Show outputs from the current workspace state."""
    client = _client()
    ws_id = client.workspace_id(workspace)
    data = client.get(f"/workspaces/{ws_id}/current-state-version", params={"include": "outputs"})
    included = data.get("included", [])
    outputs = [StateVersionOutput.model_validate(item) for item in included if item["type"] == "state-version-outputs"]
    return [o.model_dump(by_alias=True) for o in outputs]


# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------


@mcp.tool()
def list_variables(workspace: str) -> list[dict]:
    """List variables for a workspace."""
    client = _client()
    ws_id = client.workspace_id(workspace)
    data = client.get(f"/workspaces/{ws_id}/vars")
    raw_items = data.get("data", [])
    return [Variable.model_validate(i).model_dump(by_alias=True) for i in raw_items]


@mcp.tool()
def set_variable(
    workspace: str,
    key: str,
    value: str,
    category: str = "terraform",
    hcl: bool = False,
    sensitive: bool = False,
) -> str:
    """Create or update a variable in a workspace. Category: 'terraform' or 'env'."""
    client = _client()
    ws_id = client.workspace_id(workspace)

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
        client.patch(f"/workspaces/{ws_id}/vars/{existing_var.id}", payload)
        return f"Updated variable {key} in {workspace}"
    else:
        client.post(f"/workspaces/{ws_id}/vars", payload)
        return f"Created variable {key} in {workspace}"


@mcp.tool()
def delete_variable(workspace: str, key: str) -> str:
    """Delete a variable from a workspace by key name."""
    client = _client()
    ws_id = client.workspace_id(workspace)

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
    return f"Deleted variable {key} from {workspace}"


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------


@mcp.tool()
def list_orgs() -> list[dict]:
    """List organizations you have access to."""
    client = _client()
    raw = client.get_all("/organizations")
    return [Organization.model_validate(i).model_dump(by_alias=True) for i in raw]


@mcp.tool()
def show_org(name: str | None = None) -> dict:
    """Show organization details. Defaults to the current org."""
    client = _client()
    org_name = name or client.org
    data = client.get(f"/organizations/{org_name}")
    return Organization.model_validate(data["data"]).model_dump(by_alias=True)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@mcp.tool()
def list_projects() -> list[dict]:
    """List projects in the organization."""
    client = _client()
    raw = client.get_all(f"/organizations/{client.org}/projects")
    return [Project.model_validate(i).model_dump(by_alias=True) for i in raw]


@mcp.tool()
def show_project(name: str) -> dict:
    """Show project details by name."""
    client = _client()
    raw_items = client.get_all(f"/organizations/{client.org}/projects")
    for item in raw_items:
        if item["attributes"]["name"] == name:
            return Project.model_validate(item).model_dump(by_alias=True)
    raise TFCError(f"Project '{name}' not found")


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


@mcp.tool()
def list_teams() -> list[dict]:
    """List teams in the organization."""
    client = _client()
    raw = client.get_all(f"/organizations/{client.org}/teams")
    return [Team.model_validate(i).model_dump(by_alias=True) for i in raw]


@mcp.tool()
def show_team(name: str) -> dict:
    """Show team details by name."""
    client = _client()
    raw_items = client.get_all(f"/organizations/{client.org}/teams")
    for item in raw_items:
        if item["attributes"]["name"] == name:
            return Team.model_validate(item).model_dump(by_alias=True)
    raise TFCError(f"Team '{name}' not found")


# ---------------------------------------------------------------------------
# Variable Sets
# ---------------------------------------------------------------------------


def _find_varset(client: TFCClient, name: str) -> VariableSet:
    raw_items = client.get_all(f"/organizations/{client.org}/varsets")
    for item in raw_items:
        if item["attributes"]["name"] == name:
            return VariableSet.model_validate(item)
    raise TFCError(f"Variable set '{name}' not found")


def _find_project_id(client: TFCClient, name: str) -> str:
    raw_items = client.get_all(f"/organizations/{client.org}/projects")
    for item in raw_items:
        if item["attributes"]["name"] == name:
            return item["id"]
    raise TFCError(f"Project '{name}' not found")


@mcp.tool()
def list_varsets() -> list[dict]:
    """List variable sets in the organization."""
    client = _client()
    raw = client.get_all(f"/organizations/{client.org}/varsets")
    return [VariableSet.model_validate(i).model_dump(by_alias=True) for i in raw]


@mcp.tool()
def show_varset(name: str) -> dict:
    """Show variable set details and its variables."""
    client = _client()
    varset = _find_varset(client, name)
    raw_vars = client.get_all(f"/varsets/{varset.id}/relationships/vars")
    variables = [Variable.model_validate(v).model_dump(by_alias=True) for v in raw_vars]
    result = varset.model_dump(by_alias=True)
    result["variables"] = variables
    return result


@mcp.tool()
def create_varset(
    name: str,
    description: str | None = None,
    is_global: bool = False,
    priority: bool = False,
) -> dict:
    """Create a variable set."""
    client = _client()
    attrs: dict = {"name": name, "global": is_global, "priority": priority}
    if description:
        attrs["description"] = description
    payload = {"data": {"type": "varsets", "attributes": attrs}}
    data = client.post(f"/organizations/{client.org}/varsets", payload)
    return data.get("data", data)


@mcp.tool()
def delete_varset(name: str) -> str:
    """Delete a variable set by name."""
    client = _client()
    varset = _find_varset(client, name)
    client.delete(f"/varsets/{varset.id}")
    return f"Deleted variable set '{name}'"


@mcp.tool()
def add_varset_project(varset_name: str, project_name: str) -> str:
    """Apply a variable set to a project."""
    client = _client()
    varset = _find_varset(client, varset_name)
    project_id = _find_project_id(client, project_name)
    payload = {"data": [{"type": "projects", "id": project_id}]}
    client.post(f"/varsets/{varset.id}/relationships/projects", payload)
    return f"Added varset '{varset_name}' to project '{project_name}'"


@mcp.tool()
def remove_varset_project(varset_name: str, project_name: str) -> str:
    """Remove a variable set from a project."""
    client = _client()
    varset = _find_varset(client, varset_name)
    project_id = _find_project_id(client, project_name)
    payload = {"data": [{"type": "projects", "id": project_id}]}
    client.delete_with_body(f"/varsets/{varset.id}/relationships/projects", payload)
    return f"Removed varset '{varset_name}' from project '{project_name}'"


@mcp.tool()
def add_varset_var(
    varset_name: str,
    key: str,
    value: str,
    category: str = "terraform",
    hcl: bool = False,
    sensitive: bool = False,
) -> str:
    """Add or update a variable in a variable set. Category: 'terraform' or 'env'."""
    client = _client()
    varset = _find_varset(client, varset_name)

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
        client.patch(f"/varsets/{varset.id}/relationships/vars/{existing_id}", payload)
        return f"Updated variable '{key}' in varset '{varset_name}'"
    else:
        client.post(f"/varsets/{varset.id}/relationships/vars", payload)
        return f"Created variable '{key}' in varset '{varset_name}'"


@mcp.tool()
def remove_varset_var(varset_name: str, key: str) -> str:
    """Remove a variable from a variable set."""
    client = _client()
    varset = _find_varset(client, varset_name)

    raw_vars = client.get_all(f"/varsets/{varset.id}/relationships/vars")
    var_id: str | None = None
    for raw_var in raw_vars:
        if raw_var["attributes"]["key"] == key:
            var_id = raw_var["id"]
            break

    if not var_id:
        raise TFCError(f"Variable '{key}' not found in varset '{varset_name}'")

    client.delete(f"/varsets/{varset.id}/relationships/vars/{var_id}")
    return f"Removed variable '{key}' from varset '{varset_name}'"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
