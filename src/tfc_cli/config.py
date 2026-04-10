"""Token and organization resolution for TFC CLI."""

import json
import os
from pathlib import Path

from tfc_cli.client import TFCError

LOCAL_CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / ".tfc-cli.json"


def _load_local_config() -> dict[str, str]:
    """Read the local config file. Returns empty dict if missing or malformed."""
    if not LOCAL_CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(LOCAL_CONFIG_FILE.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_local_config(**updates: str) -> Path:
    """Merge updates into the local config file and write it with 0600 perms."""
    current = _load_local_config()
    current.update(updates)
    LOCAL_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_CONFIG_FILE.write_text(json.dumps(current, indent=2) + "\n")
    LOCAL_CONFIG_FILE.chmod(0o600)
    return LOCAL_CONFIG_FILE


def resolve_token(cli_token: str | None) -> str:
    """Resolve TFC API token.

    Resolution order:
    1. --token CLI flag
    2. TFC_TOKEN env var
    3. Local config file (.tfc-cli.json at project root)
    4. ~/.terraform.d/credentials.tfrc.json
    """
    if cli_token:
        return cli_token

    env_token = os.environ.get("TFC_TOKEN")
    if env_token:
        return env_token

    local_token = _load_local_config().get("token")
    if local_token:
        return local_token

    creds_path = Path.home() / ".terraform.d" / "credentials.tfrc.json"
    if creds_path.exists():
        try:
            creds = json.loads(creds_path.read_text())
            token = creds.get("credentials", {}).get("app.terraform.io", {}).get("token")
            if token:
                return token
        except json.JSONDecodeError, KeyError:
            pass

    raise TFCError(
        "No TFC token found. Set one with `tfc config set-token <token>`, "
        "or provide --token / TFC_TOKEN / ~/.terraform.d/credentials.tfrc.json."
    )


def resolve_org(cli_org: str | None) -> str:
    """Resolve TFC organization.

    Resolution order:
    1. --org CLI flag
    2. TFC_ORG env var
    3. Local config file (.tfc-cli.json at project root)
    """
    if cli_org:
        return cli_org

    env_org = os.environ.get("TFC_ORG")
    if env_org:
        return env_org

    local_org = _load_local_config().get("org")
    if local_org:
        return local_org

    raise TFCError("No TFC organization set. Run `tfc config set-org <name>`, or provide --org / TFC_ORG.")
