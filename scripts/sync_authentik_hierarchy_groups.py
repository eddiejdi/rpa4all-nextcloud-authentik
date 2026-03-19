#!/usr/bin/env python3
"""Sincroniza hierarquia (gestor/subordinados) em grupos no Authentik para uso no Nextcloud."""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


AUTHENTIK_URL = env("AUTHENTIK_URL") or f"https://{env('AUTHENTIK_SUBDOMAIN', 'auth')}.{env('RPA4ALL_DOMAIN', 'rpa4all.com')}"
AUTHENTIK_TOKEN = env("AUTHENTIK_TOKEN")
VERIFY_TLS = env("AUTHENTIK_VERIFY_TLS", "true").lower() in {"1", "true", "yes", "on"}
GROUP_PREFIX = env("RPA4ALL_TEAM_GROUP_PREFIX", "NC_TEAM_")


def api(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not AUTHENTIK_TOKEN:
        raise SystemExit("AUTHENTIK_TOKEN nao configurado")

    url = f"{AUTHENTIK_URL.rstrip('/')}/api/v3{path}"
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {AUTHENTIK_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    context = None if VERIFY_TLS else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=30, context=context) as resp:
            raw = resp.read().decode().strip()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {path}: {detail}") from exc


def list_all(path: str) -> list[dict[str, Any]]:
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        chunk = api("GET", f"{path}{'&' if '?' in path else '?'}page={page}&page_size=200")
        results = chunk.get("results") or []
        if not results:
            break
        items.extend(results)
        if not chunk.get("next"):
            break
        page += 1
    return items


def slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    return cleaned or "team"


def parse_refs(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [x.strip() for x in raw.split(",") if x.strip()]
        return values
    if isinstance(raw, list):
        values: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                values.append(item.strip())
        return values
    return []


def resolve_identity(ref: str, username_by_email: dict[str, str], all_usernames: set[str]) -> str | None:
    key = ref.strip().lower()
    if not key:
        return None
    if key in all_usernames:
        return key
    if key in username_by_email:
        return username_by_email[key]
    return None


def ensure_group(name: str, groups_by_name: dict[str, dict[str, Any]], dry_run: bool) -> str:
    existing = groups_by_name.get(name)
    if existing:
        return str(existing["pk"])
    if dry_run:
        return "__dry_run__"
    created = api("POST", "/core/groups/", {"name": name, "is_superuser": False})
    groups_by_name[name] = created
    return str(created["pk"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Nao grava mudancas no Authentik")
    parser.add_argument(
        "--export-json",
        default="",
        help="Caminho para exportar o mapeamento grupo->membros para automacao no Nextcloud",
    )
    args = parser.parse_args()

    users = [u for u in list_all("/core/users/?format=json") if u.get("is_active")]
    groups = list_all("/core/groups/?format=json")

    groups_by_name = {g.get("name", ""): g for g in groups}
    username_by_email: dict[str, str] = {}
    users_by_username: dict[str, dict[str, Any]] = {}

    for user in users:
        username = (user.get("username") or "").strip().lower()
        email = (user.get("email") or "").strip().lower()
        if username:
            users_by_username[username] = user
        if email and username:
            username_by_email[email] = username

    all_usernames = set(users_by_username)
    team_members: dict[str, set[str]] = defaultdict(set)

    for username, user in users_by_username.items():
        attrs = user.get("attributes") or {}

        subordinates_refs: list[str] = []
        for key in ("subordinates", "direct_reports", "reports"):
            subordinates_refs.extend(parse_refs(attrs.get(key)))

        manager_refs: list[str] = []
        for key in ("manager", "manager_username", "reports_to"):
            manager_refs.extend(parse_refs(attrs.get(key)))

        for ref in subordinates_refs:
            subordinate = resolve_identity(ref, username_by_email, all_usernames)
            if subordinate:
                team_members[username].add(subordinate)

        for ref in manager_refs:
            manager = resolve_identity(ref, username_by_email, all_usernames)
            if manager:
                team_members[manager].add(username)

    updates: list[tuple[str, str]] = []
    export_payload: dict[str, list[str]] = {}

    for manager, members in sorted(team_members.items()):
        if not members:
            continue

        group_name = f"{GROUP_PREFIX}{slug(manager)}"
        group_id = ensure_group(group_name, groups_by_name, args.dry_run)
        complete_members = sorted(set(members) | {manager})
        export_payload[group_name] = complete_members

        for member_username in complete_members:
            member = users_by_username.get(member_username)
            if not member:
                continue
            current_groups = set(member.get("groups") or [])
            if group_id in current_groups or group_id == "__dry_run__":
                continue
            updates.append((member_username, group_name))
            if not args.dry_run:
                new_groups = sorted(current_groups | {group_id})
                api("PATCH", f"/core/users/{member['pk']}/", {"groups": new_groups})

    print(f"Usuarios ativos analisados: {len(users_by_username)}")
    print(f"Times detectados: {len(export_payload)}")
    print(f"Associacoes aplicadas: {len(updates)}")
    for username, group_name in updates[:30]:
        print(f"  + {username} -> {group_name}")

    if args.export_json:
        with open(args.export_json, "w", encoding="utf-8") as fp:
            json.dump(export_payload, fp, indent=2, ensure_ascii=True)
        print(f"Mapa exportado: {args.export_json}")


if __name__ == "__main__":
    main()
