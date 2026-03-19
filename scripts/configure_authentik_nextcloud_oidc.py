#!/usr/bin/env python3
"""Provisiona/atualiza provider OIDC do Nextcloud no Authentik com defaults RPA4All."""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


AUTHENTIK_URL = env("AUTHENTIK_URL") or f"https://{env('AUTHENTIK_SUBDOMAIN', 'auth')}.{env('RPA4ALL_DOMAIN', 'rpa4all.com')}"
AUTHENTIK_TOKEN = env("AUTHENTIK_TOKEN")
VERIFY_TLS = env("AUTHENTIK_VERIFY_TLS", "true").lower() in {"1", "true", "yes", "on"}
DOMAIN = env("RPA4ALL_DOMAIN", "rpa4all.com")
NEXTCLOUD_SUBDOMAIN = env("NEXTCLOUD_SUBDOMAIN", "nextcloud")
NEXTCLOUD_URL = env("NEXTCLOUD_PUBLIC_URL") or f"https://{NEXTCLOUD_SUBDOMAIN}.{DOMAIN}"
CLIENT_ID = env("AUTHENTIK_NEXTCLOUD_CLIENT_ID", "authentik-nextcloud")
CLIENT_SECRET = env("AUTHENTIK_NEXTCLOUD_CLIENT_SECRET")


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    if not AUTHENTIK_TOKEN:
        raise SystemExit("AUTHENTIK_TOKEN nao configurado.")

    url = f"{AUTHENTIK_URL.rstrip('/')}/api/v3{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {AUTHENTIK_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    context = None if VERIFY_TLS else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=context) as resp:
            raw = resp.read().decode().strip()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {body}") from exc


def _first_result(path: str) -> dict | None:
    result = _request("GET", path)
    items = result.get("results") or []
    return items[0] if items else None


def _authorization_flow_pk() -> str:
    flow = _first_result("/flows/instances/?designation=authorization")
    if not flow:
        raise RuntimeError("Nenhum authorization flow encontrado no Authentik.")
    return str(flow["pk"])


def _scope_mapping_pks() -> list[str]:
    try:
        result = _request("GET", "/propertymappings/provider/scope/?page_size=200")
    except RuntimeError:
        result = _request("GET", "/propertymappings/scope/?page_size=200")
    mappings = result.get("results") or []
    return [str(m["pk"]) for m in mappings]


def ensure_provider_and_app() -> None:
    flow_pk = _authorization_flow_pk()
    mappings = _scope_mapping_pks()

    redirect_uris = "\n".join(
        [
            f"{NEXTCLOUD_URL}/apps/oidc_login/oidc",
            f"{NEXTCLOUD_URL}/apps/user_oidc/code",
        ]
    )

    provider_payload = {
        "name": "RPA4All Nextcloud Provider",
        "authorization_flow": flow_pk,
        "client_type": "confidential",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uris": redirect_uris,
        "property_mappings": mappings,
        "sub_mode": "hashed_user_id",
        "include_claims_in_id_token": True,
        "issuer_mode": "per_provider",
    }

    if not CLIENT_SECRET:
        raise SystemExit("AUTHENTIK_NEXTCLOUD_CLIENT_SECRET nao configurado.")

    existing_provider = _first_result(
        f"/providers/oauth2/?search={urllib.parse.quote(CLIENT_ID)}"
    )
    if existing_provider:
        pk = existing_provider["pk"]
        _request("PATCH", f"/providers/oauth2/{pk}/", provider_payload)
        provider_pk = pk
        print(f"Provider atualizado: {provider_pk}")
    else:
        created = _request("POST", "/providers/oauth2/", provider_payload)
        provider_pk = created["pk"]
        print(f"Provider criado: {provider_pk}")

    app_payload = {
        "name": "Nextcloud",
        "slug": "nextcloud",
        "provider": provider_pk,
        "meta_launch_url": NEXTCLOUD_URL,
        "policy_engine_mode": "any",
    }

    existing_app = _first_result("/core/applications/?search=nextcloud")
    if existing_app:
        _request("PATCH", "/core/applications/nextcloud/", app_payload)
        print("Application atualizada: nextcloud")
    else:
        _request("POST", "/core/applications/", app_payload)
        print("Application criada: nextcloud")

    print(f"Nextcloud URL: {NEXTCLOUD_URL}")
    print(f"Authentik URL: {AUTHENTIK_URL}")


if __name__ == "__main__":
    ensure_provider_and_app()
