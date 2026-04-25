#!/usr/bin/env python3
"""Revoga tokens e sessões de um usuário, forçando re-login no Authentik e Nextcloud."""
from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


AUTHENTIK_URL = env("AUTHENTIK_URL") or f"https://{env('AUTHENTIK_SUBDOMAIN', 'auth')}.{env('RPA4ALL_DOMAIN', 'rpa4all.com')}"
AUTHENTIK_TOKEN = env("AUTHENTIK_TOKEN")
VERIFY_TLS = env("AUTHENTIK_VERIFY_TLS", "true").lower() in {"1", "true", "yes", "on"}
NEXTCLOUD_CONTAINER = env("NEXTCLOUD_CONTAINER", "nextcloud-rpa4all")


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
        sep = "&" if "?" in path else "?"
        chunk = api("GET", f"{path}{sep}page={page}&page_size=200")
        results = chunk.get("results") or []
        if not results:
            break
        items.extend(results)
        if not chunk.get("next"):
            break
        page += 1
    return items


def run_occ(container: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["docker", "exec", "-u", "www-data", container, "php", "occ", *args]
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def find_user(identity: str, verbose: bool) -> dict[str, Any]:
    identity_q = urllib.parse.quote(identity)
    for field in ("username", "email"):
        results = api("GET", f"/core/users/?{field}={identity_q}").get("results") or []
        if results:
            user = results[0]
            if verbose:
                print(f"  encontrado por {field}: pk={user['pk']} username={user['username']}")
            return user
    print(f"Erro: usuário '{identity}' não encontrado no Authentik.", file=sys.stderr)
    sys.exit(1)


def revoke_core_tokens(user_pk: int, dry_run: bool, verbose: bool) -> int:
    tokens = list_all(f"/core/tokens/?user_id={user_pk}")
    count = 0
    for token in tokens:
        key = token.get("key") or token.get("pk")
        if not key:
            continue
        if dry_run:
            print(f"  [dry-run] DELETE /core/tokens/{key}/")
        else:
            try:
                api("DELETE", f"/core/tokens/{key}/")
                if verbose:
                    print(f"  revogado token interno: {key}")
            except RuntimeError as exc:
                print(f"  aviso: {exc}", file=sys.stderr)
        count += 1
    return count


def revoke_oauth2_refresh_tokens(user_pk: int, dry_run: bool, verbose: bool) -> int:
    tokens = list_all(f"/oauth2/refresh-tokens/?user={user_pk}")
    count = 0
    for token in tokens:
        pk = token.get("pk")
        if pk is None:
            continue
        if dry_run:
            print(f"  [dry-run] DELETE /oauth2/refresh-tokens/{pk}/")
        else:
            try:
                api("DELETE", f"/oauth2/refresh-tokens/{pk}/")
                if verbose:
                    print(f"  revogado refresh token pk={pk}")
            except RuntimeError as exc:
                print(f"  aviso: {exc}", file=sys.stderr)
        count += 1
    return count


def revoke_oauth2_access_tokens(user_pk: int, dry_run: bool, verbose: bool) -> int:
    tokens = list_all(f"/oauth2/access-tokens/?user={user_pk}")
    count = 0
    for token in tokens:
        pk = token.get("pk")
        if pk is None:
            continue
        if dry_run:
            print(f"  [dry-run] DELETE /oauth2/access-tokens/{pk}/")
        else:
            try:
                api("DELETE", f"/oauth2/access-tokens/{pk}/")
                if verbose:
                    print(f"  revogado access token pk={pk}")
            except RuntimeError as exc:
                print(f"  aviso: {exc}", file=sys.stderr)
        count += 1
    return count


def revoke_nextcloud_sessions(username: str, container: str, dry_run: bool, verbose: bool) -> None:
    if dry_run:
        print(f"  [dry-run] occ user:auth:reset-password {username}")
        print(f"  [dry-run] occ user:session:list {username}")
        return

    proc = run_occ(container, "user:auth:reset-password", username, check=False)
    if proc.returncode == 0:
        if verbose:
            print(f"  app passwords de '{username}' invalidados")
    else:
        print(f"  aviso: user:auth:reset-password falhou: {proc.stderr.strip()}", file=sys.stderr)

    proc = run_occ(container, "user:session:list", username, "--output=json", check=False)
    if proc.returncode != 0:
        if verbose:
            print("  occ user:session:list indisponível, pulando revogação de sessões web")
        return

    try:
        sessions = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return

    for session in sessions:
        token = session.get("token") or session.get("id")
        if not token:
            continue
        result = run_occ(container, "user:session:delete", username, str(token), check=False)
        if verbose:
            status = "ok" if result.returncode == 0 else f"falhou: {result.stderr.strip()}"
            print(f"  sessão {token}: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity", help="Username ou email do usuário")
    parser.add_argument("--dry-run", action="store_true", help="Simula ações sem executar")
    parser.add_argument("--verbose", action="store_true", help="Imprime detalhes de cada token")
    parser.add_argument("--skip-authentik", action="store_true", help="Pula revogação no Authentik")
    parser.add_argument("--skip-nextcloud", action="store_true", help="Pula revogação no Nextcloud")
    args = parser.parse_args()

    user = find_user(args.identity, args.verbose)
    user_pk: int = user["pk"]
    username: str = user["username"]
    print(f"Usuário: {username} (pk={user_pk})")

    if not args.skip_authentik:
        total = 0
        total += revoke_core_tokens(user_pk, args.dry_run, args.verbose)
        total += revoke_oauth2_refresh_tokens(user_pk, args.dry_run, args.verbose)
        total += revoke_oauth2_access_tokens(user_pk, args.dry_run, args.verbose)
        print(f"Tokens Authentik revogados: {total}" + (" [dry-run]" if args.dry_run else ""))

    if not args.skip_nextcloud:
        print("Revogando sessões Nextcloud...")
        revoke_nextcloud_sessions(username, NEXTCLOUD_CONTAINER, args.dry_run, args.verbose)

    print("Re-login forçado concluído." + (" [dry-run]" if args.dry_run else ""))


if __name__ == "__main__":
    main()
