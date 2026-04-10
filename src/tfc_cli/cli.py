"""Main CLI entry point with global options."""

import json as json_mod
import sys

import click
from rich.console import Console
from rich.text import Text

from tfc_cli.client import TFCClient, TFCError
from tfc_cli.config import resolve_org, resolve_token

pass_client = click.make_pass_decorator(TFCClient, ensure=True)


class Context:
    """Holds CLI options and lazily constructs the TFC client on first access."""

    def __init__(self) -> None:
        self._token_arg: str | None = None
        self._org_arg: str | None = None
        self._client: TFCClient | None = None
        self.json_output: bool = False

    @property
    def client(self) -> TFCClient:
        if self._client is None:
            token = resolve_token(self._token_arg)
            org = resolve_org(self._org_arg)
            self._client = TFCClient(token, org)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()


pass_context = click.make_pass_decorator(Context, ensure=True)


def _format_params(cmd: click.Command) -> str:
    """Format a command's arguments and key options into a compact signature."""
    parts: list[str] = []
    for param in cmd.params:
        if isinstance(param, click.Argument):
            raw = param.name.upper().replace("_", "-")
            name = f"[{raw}]" if not param.required else f"<{raw}>"
            parts.append(name)
        elif isinstance(param, click.Option) and param.name not in ("help",):
            opts = param.opts[0]
            if param.is_flag:
                parts.append(f"[{opts}]")
            else:
                parts.append(f"[{opts} {param.type.name.upper()}]")
    return " ".join(parts)


def _print_rich_help(group: click.Group) -> None:
    """Print the rich help output for the CLI."""
    console = Console()
    console.print("[bold]tfc[/bold] — Terraform Cloud CLI\n")
    console.print("[dim]Global options: --token TEXT  --org TEXT  --json[/dim]\n")

    for cmd_name in sorted(group.commands):
        cmd = group.commands[cmd_name]
        if cmd_name == "help":
            continue

        if isinstance(cmd, click.Group):
            console.print(f"[bold cyan]{cmd_name}[/bold cyan]  [dim]{cmd.get_short_help_str()}[/dim]")
            for sub_name in sorted(cmd.commands):
                sub_cmd = cmd.commands[sub_name]
                params_str = _format_params(sub_cmd)
                line = Text()
                line.append(f"  tfc {cmd_name} {sub_name}", style="green")
                if params_str:
                    line.append(f" {params_str}", style="yellow")
                short_help = sub_cmd.get_short_help_str()
                if short_help:
                    padding = max(1, 55 - len(line.plain))
                    line.append(" " * padding)
                    line.append(short_help, style="dim")
                console.print(line)
        else:
            params_str = _format_params(cmd)
            line = Text()
            line.append(f"  tfc {cmd_name}", style="green")
            if params_str:
                line.append(f" {params_str}", style="yellow")
            short_help = cmd.get_short_help_str()
            if short_help:
                padding = max(1, 55 - len(line.plain))
                line.append(" " * padding)
                line.append(short_help, style="dim")
            console.print(f"[bold cyan]{cmd_name}[/bold cyan]")
            console.print(line)
        console.print()


class RichGroup(click.Group):
    """Click group that uses rich help output for --help."""

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        _print_rich_help(self)

    def invoke(self, ctx: click.Context) -> None:
        try:
            return super().invoke(ctx)
        except TFCError as exc:
            click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
            sys.exit(1)


@click.group(cls=RichGroup)
@click.option(
    "--token",
    default=None,
    envvar="TFC_TOKEN",
    help="TFC API token (optional: falls back to TFC_TOKEN env var, then ~/.terraform.d/credentials.tfrc.json)",
)
@click.option("--org", default=None, envvar="TFC_ORG", help="TFC organization")
@click.option("--json", "json_output", is_flag=True, help="Output raw JSON")
@click.pass_context
def cli(ctx: click.Context, token: str | None, org: str | None, json_output: bool) -> None:
    """Terraform Cloud CLI — manage workspaces, runs, plans, state, and variables."""
    ctx.ensure_object(Context)
    ctx.obj._token_arg = token
    ctx.obj._org_arg = org
    ctx.obj.json_output = json_output
    ctx.call_on_close(ctx.obj.close)


def output_json(data: dict | list) -> None:
    """Print JSON to stdout."""
    click.echo(json_mod.dumps(data, indent=2))


# Register command groups
from tfc_cli.commands.applies import applies  # noqa: E402
from tfc_cli.commands.config_cmd import config_group  # noqa: E402
from tfc_cli.commands.orgs import orgs  # noqa: E402
from tfc_cli.commands.plans import plans  # noqa: E402
from tfc_cli.commands.projects import projects  # noqa: E402
from tfc_cli.commands.runs import runs  # noqa: E402
from tfc_cli.commands.state import state  # noqa: E402
from tfc_cli.commands.teams import teams  # noqa: E402
from tfc_cli.commands.variables import vars_group  # noqa: E402
from tfc_cli.commands.varsets import varsets  # noqa: E402
from tfc_cli.commands.workspaces import workspaces  # noqa: E402

cli.add_command(workspaces)
cli.add_command(runs)
cli.add_command(plans)
cli.add_command(applies)
cli.add_command(state)
cli.add_command(vars_group)
cli.add_command(orgs)
cli.add_command(projects)
cli.add_command(teams)
cli.add_command(varsets)
cli.add_command(config_group)


@cli.command("help")
@click.pass_context
def help_cmd(ctx: click.Context) -> None:
    """Show all commands with their arguments."""
    parent = ctx.parent
    assert parent is not None
    _print_rich_help(parent.command)
