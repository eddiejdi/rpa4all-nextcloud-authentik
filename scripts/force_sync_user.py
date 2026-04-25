#!/usr/bin/env python3
"""Força re-scan de arquivos no servidor Nextcloud e (opcionalmente) reseta o cliente desktop."""
from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


NEXTCLOUD_CONTAINER = env("NEXTCLOUD_CONTAINER", "nextcloud-rpa4all")


def run_occ(container: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["docker", "exec", "-u", "www-data", container, "php", "occ", *args]
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def scan_files(username: str, container: str, dry_run: bool, verbose: bool) -> None:
    path = f"/{username}/files"
    if dry_run:
        print(f"  [dry-run] occ files:scan --path={path}")
        return
    print(f"Escaneando arquivos de '{username}'...")
    proc = run_occ(container, "files:scan", f"--path={path}", check=False)
    if proc.returncode == 0:
        if verbose:
            print(proc.stdout.strip())
    else:
        print(f"  aviso: files:scan retornou erro: {proc.stderr.strip()}", file=sys.stderr)


def cleanup_files(container: str, dry_run: bool, verbose: bool) -> None:
    if dry_run:
        print("  [dry-run] occ files:cleanup")
        return
    print("Limpando arquivos órfãos...")
    proc = run_occ(container, "files:cleanup", check=False)
    if proc.returncode == 0:
        if verbose:
            print(proc.stdout.strip())
    else:
        print(f"  aviso: files:cleanup retornou erro: {proc.stderr.strip()}", file=sys.stderr)


def send_notification(username: str, container: str, dry_run: bool, verbose: bool) -> None:
    subject = "Sincronização forçada"
    message = "Seus arquivos foram re-escaneados pelo servidor."
    if dry_run:
        print(f"  [dry-run] occ notification:generate {username} \"{subject}\"")
        return
    proc = run_occ(container, "notification:generate", username, subject, message, check=False)
    if proc.returncode == 0:
        if verbose:
            print(f"  notificação enviada para '{username}'")
    else:
        if verbose:
            print("  aviso: notification:generate indisponível (app admin_notifications não instalado)")


def find_client_journals(journal_path: str | None, username: str, verbose: bool) -> list[str]:
    if journal_path:
        patterns = [journal_path]
    else:
        patterns = [
            "~/.local/share/Nextcloud/*/journal.db",
            "~/RPA4AllFiles/.sync_nextcloud.*.db",
            "~/.config/Nextcloud/*/journal.db",
        ]

    found: list[str] = []
    for pattern in patterns:
        expanded = os.path.expanduser(pattern)
        for path in glob.glob(expanded):
            if os.path.exists(path):
                found.append(path)
                if verbose:
                    print(f"  journal encontrado: {path}")

    if not found and verbose:
        print("  nenhum journal de sync encontrado")

    return found


def reset_client(journal_path: str | None, username: str, dry_run: bool, verbose: bool) -> None:
    if dry_run:
        print("  [dry-run] pkill -f rpa4all-files")
        journals = find_client_journals(journal_path, username, verbose)
        for path in journals:
            print(f"  [dry-run] rm {path}")
        print("  [dry-run] /usr/bin/rpa4all-files --background")
        return

    subprocess.run(["pkill", "-f", "rpa4all-files"], check=False)

    journals = find_client_journals(journal_path, username, verbose)
    for path in journals:
        try:
            os.remove(path)
            if verbose:
                print(f"  removido journal: {path}")
        except OSError as exc:
            print(f"  aviso: não foi possível remover {path}: {exc}", file=sys.stderr)

    binary = "/usr/bin/rpa4all-files"
    if not os.path.exists(binary):
        import shutil
        binary_in_path = shutil.which("rpa4all-files")
        if binary_in_path:
            binary = binary_in_path
        else:
            print("  aviso: rpa4all-files não encontrado, cliente não reiniciado", file=sys.stderr)
            return

    subprocess.Popen([binary, "--background"], start_new_session=True)
    if verbose:
        print(f"  cliente reiniciado: {binary} --background")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="Username no Nextcloud")
    parser.add_argument("--dry-run", action="store_true", help="Simula ações sem executar")
    parser.add_argument("--verbose", action="store_true", help="Imprime detalhes de cada ação")
    parser.add_argument("--cleanup", action="store_true", help="Executa occ files:cleanup após o scan")
    parser.add_argument("--reset-client", action="store_true",
                        help="Reseta journal do cliente desktop e reinicia o processo")
    parser.add_argument("--client-journal-path", default="", metavar="PATH",
                        help="Caminho (ou glob) para o journal.db do cliente. Padrão: busca automática")
    parser.add_argument("--no-notification", action="store_true",
                        help="Não envia notificação in-app ao usuário")
    args = parser.parse_args()

    scan_files(args.username, NEXTCLOUD_CONTAINER, args.dry_run, args.verbose)

    if args.cleanup:
        cleanup_files(NEXTCLOUD_CONTAINER, args.dry_run, args.verbose)

    if not args.no_notification:
        send_notification(args.username, NEXTCLOUD_CONTAINER, args.dry_run, args.verbose)

    if args.reset_client:
        print("Resetando cliente desktop...")
        reset_client(
            args.client_journal_path or None,
            args.username,
            args.dry_run,
            args.verbose,
        )

    print("Force sync concluído." + (" [dry-run]" if args.dry_run else ""))


if __name__ == "__main__":
    main()
