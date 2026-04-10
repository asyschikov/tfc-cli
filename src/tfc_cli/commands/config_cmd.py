"""Local config file management (token + org persistence)."""

import click

from tfc_cli.config import LOCAL_CONFIG_FILE, save_local_config


@click.group("config")
def config_group() -> None:
    """Manage the local config file (token, org)."""


@config_group.command("set-token")
@click.argument("token")
def config_set_token(token: str) -> None:
    """Save a TFC API token to the local config file."""
    path = save_local_config(token=token)
    click.echo(f"Saved token to {path}")


@config_group.command("set-org")
@click.argument("org")
def config_set_org(org: str) -> None:
    """Save the default TFC organization to the local config file."""
    path = save_local_config(org=org)
    click.echo(f"Saved org '{org}' to {path}")


@config_group.command("path")
def config_path() -> None:
    """Print the path to the local config file."""
    click.echo(str(LOCAL_CONFIG_FILE))
