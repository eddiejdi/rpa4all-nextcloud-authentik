# Fork RPA4All: Nextcloud + Authentik

Fork operacional para RPA4All com 3 objetivos:

- Sem configuração manual de URL (usa defaults `nextcloud.rpa4all.com` e `auth.rpa4all.com`).
- Login federado via Authentik (OIDC).
- Perfil e grupos do usuario seguindo o Authentik, incluindo hierarquia gestor/subordinados para controle de acesso por grupo.

## Estrutura

- `docker-compose.yml`: stack Nextcloud + MariaDB + Redis.
- `scripts/configure_authentik_nextcloud_oidc.py`: cria/atualiza provider OIDC do Nextcloud no Authentik.
- `scripts/bootstrap_nextcloud_oidc.sh`: instala apps e aplica OIDC/config no Nextcloud sem editar URL manualmente.
- `scripts/sync_authentik_hierarchy_groups.py`: cria grupos de equipe no Authentik com base na hierarquia (gestor/subordinados).
- `scripts/apply_nextcloud_team_folders.py`: aplica grupos e Group Folders no Nextcloud para restringir acesso por equipe.
- `scripts/generate_nextcloud_background.py`: gera SVG de fundo no mesmo padrão lógico do `www.rpa4all.com` (contexto Brasil + prompt dinâmico via LLM).
- `scripts/apply_nextcloud_background.sh`: publica o SVG no theming do Nextcloud como background global.

## Pré-requisitos

- Docker e Docker Compose.
- Instância Authentik ativa.
- Token de API do Authentik (`AUTHENTIK_TOKEN`).
- Plugin `oidc_login` e `groupfolders` no Nextcloud (o bootstrap instala automaticamente).

## Uso rápido

1. Criar env local:

```bash
cd forks/rpa4all-nextcloud-authentik
cp .env.example .env
```

2. Subir stack:

```bash
docker compose --env-file .env up -d
```

3. Provisionar provider OIDC no Authentik:

```bash
set -a; source .env; set +a
python3 scripts/configure_authentik_nextcloud_oidc.py
```

4. Aplicar bootstrap OIDC no Nextcloud:

```bash
set -a; source .env; set +a
bash scripts/bootstrap_nextcloud_oidc.sh
```

5. Sincronizar hierarquia do Authentik para grupos de equipe:

```bash
set -a; source .env; set +a
python3 scripts/sync_authentik_hierarchy_groups.py --export-json /tmp/rpa4all_teams.json
```

6. Aplicar grupos/pastas por equipe no Nextcloud:

```bash
set -a; source .env; set +a
python3 scripts/apply_nextcloud_team_folders.py /tmp/rpa4all_teams.json
```

7. Gerar e aplicar fundo no padrão do RPA4All.com:

```bash
set -a; source .env; set +a
python3 scripts/generate_nextcloud_background.py \
  --api-base "${RPA4ALL_BG_API_BASE}" \
  --model "${RPA4ALL_BG_MODEL}" \
  --output /tmp/rpa4all-nextcloud-bg.svg

NEXTCLOUD_CONTAINER=nextcloud bash scripts/apply_nextcloud_background.sh /tmp/rpa4all-nextcloud-bg.svg
```

8. (Opcional) atualizar automaticamente 1x por dia:

```bash
0 5 * * * cd /caminho/forks/rpa4all-nextcloud-authentik && \
  . ./.env && \
  python3 scripts/generate_nextcloud_background.py --api-base "$RPA4ALL_BG_API_BASE" --model "$RPA4ALL_BG_MODEL" --output /tmp/rpa4all-nextcloud-bg.svg && \
  NEXTCLOUD_CONTAINER=nextcloud bash scripts/apply_nextcloud_background.sh /tmp/rpa4all-nextcloud-bg.svg
```

## Modelo de hierarquia no Authentik

O script de sync lê os atributos do usuario no Authentik e aceita estes campos:

- Subordinados: `subordinates`, `direct_reports`, `reports`
- Gestor: `manager`, `manager_username`, `reports_to`

Valores podem ser `username`, `email`, lista ou string separada por virgula.

## Resultado esperado

- Usuário loga no Nextcloud com Authentik.
- Perfil (nome/email/username) segue claims OIDC.
- Equipes viram grupos `NC_TEAM_<gestor>`.
- Group Folder por equipe, com acesso restrito ao proprio grupo.

## Observações

- Se seu domínio não for `rpa4all.com`, altere apenas `RPA4ALL_DOMAIN` no `.env`.
- Se o comando de permissões do Group Folders variar entre versões, o script mostra fallback e orienta ajuste manual pontual.
