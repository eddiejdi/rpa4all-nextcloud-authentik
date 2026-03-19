#!/usr/bin/env python3
"""Aplica grupos e pastas por time no Nextcloud, baseado em JSON exportado do Authentik."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys


def run_occ(container: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["docker", "exec", "-u", "www-data", container, "php", "occ", *args]
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def ensure_group(container: str, group: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] group:add {group}")
        return
    proc = run_occ(container, "group:add", group, check=False)
    if proc.returncode == 0:
        print(f"Grupo criado: {group}")
        return
    if "already exists" in (proc.stdout + proc.stderr).lower():
        print(f"Grupo existente: {group}")
        return
    print(proc.stdout + proc.stderr, file=sys.stderr)


def parse_groupfolders_list(output: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in output.splitlines():
        pipe = re.match(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", line)
        if pipe:
            mapping[pipe.group(2).strip()] = pipe.group(1).strip()
            continue
        # Tenta capturar formatos comuns: "1 - Financeiro" ou "1  Financeiro"
        m = re.match(r"\s*(\d+)\s*[-|:]?\s+(.+?)\s*$", line)
        if m:
            mapping[m.group(2).strip()] = m.group(1).strip()
    return mapping


def ensure_groupfolder(container: str, folder_name: str, dry_run: bool) -> str | None:
    if dry_run:
        print(f"[dry-run] groupfolders:create {folder_name}")
        return "0"

    listed = run_occ(container, "groupfolders:list", check=False)
    folders = parse_groupfolders_list(listed.stdout + "\n" + listed.stderr)
    if folder_name in folders:
        return folders[folder_name]

    created = run_occ(container, "groupfolders:create", folder_name, check=False)
    text = created.stdout + "\n" + created.stderr
    m = re.search(r"(id|folder)\D+(\d+)", text, flags=re.IGNORECASE)
    if m:
        return m.group(2)

    listed = run_occ(container, "groupfolders:list", check=False)
    folders = parse_groupfolders_list(listed.stdout + "\n" + listed.stderr)
    return folders.get(folder_name)


def grant_group_access(container: str, folder_id: str, group_name: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] groupfolders:group {folder_id} {group_name} read write share delete")
        return

    attempts = [
        ["groupfolders:group", folder_id, group_name, "read", "write", "share", "delete"],
        ["groupfolders:group", folder_id, group_name, "1", "1", "1", "1"],
    ]
    for args in attempts:
        proc = run_occ(container, *args, check=False)
        if proc.returncode == 0:
            print(f"Permissao aplicada: pasta {folder_id} -> grupo {group_name}")
            return
    print(
        f"Nao foi possivel aplicar permissoes automaticas para {group_name}. Ajuste manual em Group Folders.",
        file=sys.stderr,
    )


def add_members_to_group(container: str, group: str, users: list[str], dry_run: bool) -> None:
    for user in users:
        if dry_run:
            print(f"[dry-run] group:adduser {group} {user}")
            continue
        proc = run_occ(container, "group:adduser", group, user, check=False)
        if proc.returncode == 0 or "already" in (proc.stdout + proc.stderr).lower():
            continue
        print(f"Falha ao adicionar {user} em {group}: {proc.stdout}{proc.stderr}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mapping_json", help="JSON com mapeamento grupo->membros")
    parser.add_argument("--container", default=os.getenv("NEXTCLOUD_CONTAINER", "nextcloud-rpa4all"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(args.mapping_json, "r", encoding="utf-8") as fp:
        mapping = json.load(fp)

    if not isinstance(mapping, dict):
        raise SystemExit("JSON invalido: esperado objeto com grupo->lista de usuarios")

    for group, members in mapping.items():
        if not isinstance(members, list):
            continue
        ensure_group(args.container, group, args.dry_run)
        add_members_to_group(args.container, group, [str(x) for x in members], args.dry_run)

        folder_id = ensure_groupfolder(args.container, group, args.dry_run)
        if folder_id:
            grant_group_access(args.container, folder_id, group, args.dry_run)

    print("Sincronizacao de grupos/pastas concluida")


if __name__ == "__main__":
    main()
