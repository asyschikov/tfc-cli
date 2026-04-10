"""TFC API client with auth, pagination, and workspace resolution."""

from typing import Any

import httpx

BASE_URL = "https://app.terraform.io/api/v2"


class TFCError(Exception):
    """Raised on TFC API errors."""


class TFCClient:
    """Terraform Cloud API client."""

    def __init__(self, token: str, org: str) -> None:
        self.token = token
        self.org = org
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/vnd.api+json",
            },
            timeout=30.0,
        )
        self._workspace_id_cache: dict[str, str] = {}

    def close(self) -> None:
        self._http.close()

    def _handle_error(self, resp: httpx.Response) -> None:
        if resp.is_success:
            return
        status = resp.status_code
        labels = {
            401: "Unauthorized — check your token",
            403: "Forbidden — insufficient permissions",
            404: "Not found",
            409: "Conflict — resource is in an incompatible state",
            429: "Rate limited — try again later",
        }
        msg = labels.get(status, f"HTTP {status}")
        try:
            body = resp.json()
            errors = body.get("errors", [])
            if errors:
                details = "; ".join(e.get("detail", e.get("title", str(e))) for e in errors)
                msg = f"{msg}: {details}"
        except Exception:
            pass
        raise TFCError(msg)

    # --- low-level requests ---

    def get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        resp = self._http.get(path, params=params)
        self._handle_error(resp)
        return resp.json()

    def post(self, path: str, payload: dict | None = None) -> dict[str, Any]:
        resp = self._http.post(path, json=payload)
        self._handle_error(resp)
        if resp.status_code == 204:
            return {}
        return resp.json()

    def patch(self, path: str, payload: dict | None = None) -> dict[str, Any]:
        resp = self._http.patch(path, json=payload)
        self._handle_error(resp)
        if resp.status_code == 204:
            return {}
        return resp.json()

    def delete(self, path: str) -> None:
        resp = self._http.delete(path)
        self._handle_error(resp)

    def delete_with_body(self, path: str, payload: dict) -> None:
        """DELETE with a JSON body (used for relationship removals)."""
        resp = self._http.request("DELETE", path, json=payload)
        self._handle_error(resp)

    def get_raw(self, url: str) -> str:
        """GET a raw URL (e.g. archivist URLs for logs/state). Returns text."""
        resp = self._http.get(url, headers={"Accept": "text/plain"})
        self._handle_error(resp)
        return resp.text

    def get_raw_bytes(self, url: str) -> bytes:
        """GET a raw URL returning bytes (for state downloads)."""
        resp = self._http.get(url)
        self._handle_error(resp)
        return resp.content

    # --- pagination ---

    def get_all(self, path: str, params: dict | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        """Auto-paginate a list endpoint. Returns all data items."""
        params = dict(params or {})
        params.setdefault("page[size]", 20)
        items: list[dict[str, Any]] = []

        while True:
            resp = self.get(path, params=params)
            data = resp.get("data", [])
            items.extend(data)

            if limit and len(items) >= limit:
                return items[:limit]

            next_page = resp.get("meta", {}).get("pagination", {}).get("next-page")
            if not next_page:
                break
            params["page[number]"] = next_page

        return items

    # --- workspace resolution ---

    def workspace_id(self, name: str) -> str:
        """Resolve workspace name to ID, with per-session caching."""
        if name in self._workspace_id_cache:
            return self._workspace_id_cache[name]

        data = self.get(f"/organizations/{self.org}/workspaces/{name}")
        ws_id = data["data"]["id"]
        self._workspace_id_cache[name] = ws_id
        return ws_id
