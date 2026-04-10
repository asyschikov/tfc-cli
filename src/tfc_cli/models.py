"""Pydantic models for TFC API responses."""

from pydantic import BaseModel, ConfigDict, Field


def to_kebab(name: str) -> str:
    """Convert snake_case to kebab-case for TFC JSON:API field names."""
    return name.replace("_", "-")


class TFCModel(BaseModel):
    """Base model with kebab-case alias generation for TFC API compatibility."""

    model_config = ConfigDict(alias_generator=to_kebab, populate_by_name=True)


# --- Workspaces ---


class VcsRepo(TFCModel):
    identifier: str | None = None
    branch: str | None = None


class WorkspaceAttributes(TFCModel):
    name: str
    terraform_version: str | None = None
    execution_mode: str | None = None
    auto_apply: bool = False
    locked: bool = False
    vcs_repo: VcsRepo | None = None
    working_directory: str | None = None
    resource_count: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class Workspace(TFCModel):
    id: str
    attributes: WorkspaceAttributes


# --- Runs ---


class RunActions(TFCModel):
    is_confirmable: bool = False
    is_discardable: bool = False
    is_cancelable: bool = False


class RunAttributes(TFCModel):
    status: str
    message: str | None = None
    source: str | None = None
    trigger_reason: str | None = None
    auto_apply: bool = False
    is_destroy: bool = False
    created_at: str | None = None
    actions: RunActions = RunActions()


class RelationshipData(TFCModel):
    id: str
    type: str


class Relationship(TFCModel):
    data: RelationshipData | None = None


class RunRelationships(TFCModel):
    plan: Relationship = Relationship()
    apply: Relationship = Relationship()


class Run(TFCModel):
    id: str
    attributes: RunAttributes
    relationships: RunRelationships = RunRelationships()


# --- Plans ---


class PlanAttributes(TFCModel):
    status: str | None = None
    has_changes: bool = False
    resource_additions: int | None = None
    resource_changes: int | None = None
    resource_destructions: int | None = None
    output_additions: int | None = None
    output_changes: int | None = None
    output_destructions: int | None = None
    log_read_url: str | None = None


class Plan(TFCModel):
    id: str
    attributes: PlanAttributes


# --- Applies ---


class ApplyAttributes(TFCModel):
    status: str | None = None
    resource_additions: int | None = None
    resource_changes: int | None = None
    resource_destructions: int | None = None
    resource_imports: int | None = None
    log_read_url: str | None = None


class Apply(TFCModel):
    id: str
    attributes: ApplyAttributes


# --- State Versions ---


class StateVersionAttributes(TFCModel):
    serial: int | None = None
    terraform_version: str | None = None
    resources_processed: int | None = None
    created_at: str | None = None
    size: int | None = None
    hosted_state_download_url: str | None = None


class StateVersion(TFCModel):
    id: str
    attributes: StateVersionAttributes


class StateVersionOutputAttributes(TFCModel):
    name: str | None = None
    value: str | int | float | bool | list | dict | None = None
    sensitive: bool = False
    type: str | None = None


class StateVersionOutput(TFCModel):
    id: str
    type: str
    attributes: StateVersionOutputAttributes


# --- Variables ---


class VariableAttributes(TFCModel):
    key: str
    value: str | None = None
    category: str | None = None
    hcl: bool = False
    sensitive: bool = False


class Variable(TFCModel):
    id: str
    attributes: VariableAttributes


# --- Organizations ---


# --- Projects ---


class ProjectPermissions(TFCModel):
    can_read: bool = False
    can_update: bool = False
    can_create_workspace: bool = False
    can_manage_teams: bool = False
    can_read_teams: bool = False


class ProjectAttributes(TFCModel):
    name: str
    description: str | None = None
    workspace_count: int | None = None
    team_count: int | None = None
    default_execution_mode: str | None = None
    permissions: ProjectPermissions = ProjectPermissions()
    created_at: str | None = None


class Project(TFCModel):
    id: str
    attributes: ProjectAttributes


# --- Teams ---


class TeamOrgAccess(TFCModel):
    manage_workspaces: bool = False
    manage_projects: bool = False
    manage_vcs_settings: bool = False
    manage_policies: bool = False
    manage_modules: bool = False
    manage_providers: bool = False
    manage_membership: bool = False


class TeamAttributes(TFCModel):
    name: str
    organization_access: TeamOrgAccess = TeamOrgAccess()
    users_count: int | None = None
    visibility: str | None = None


class Team(TFCModel):
    id: str
    attributes: TeamAttributes


# --- Team Access ---


class TeamAccessAttributes(TFCModel):
    access: str


class TeamAccessRelationships(TFCModel):
    workspace: Relationship = Relationship()
    team: Relationship = Relationship()


class TeamAccess(TFCModel):
    id: str
    attributes: TeamAccessAttributes
    relationships: TeamAccessRelationships = TeamAccessRelationships()


# --- Variable Sets ---


class VariableSetAttributes(TFCModel):
    name: str
    description: str | None = None
    is_global: bool = Field(False, alias="global")
    priority: bool = False
    var_count: int | None = None
    workspace_count: int | None = None
    project_count: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class VariableSetRelationships(TFCModel):
    vars: Relationship = Relationship()
    workspaces: Relationship = Relationship()
    projects: Relationship = Relationship()


class VariableSet(TFCModel):
    id: str
    attributes: VariableSetAttributes
    relationships: VariableSetRelationships = VariableSetRelationships()


# --- Organizations ---


class OrgAttributes(TFCModel):
    name: str
    email: str | None = None
    plan: str | None = None
    cost_estimation_enabled: bool = False
    sentinel_enabled: bool = False
    run_task_limit: int | None = None
    created_at: str | None = None


class Organization(TFCModel):
    id: str
    attributes: OrgAttributes
