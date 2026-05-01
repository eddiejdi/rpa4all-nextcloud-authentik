#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${NEXTCLOUD_CONTAINER:-nextcloud-rpa4all}"
DOMAIN="${RPA4ALL_DOMAIN:-rpa4all.com}"
NC_SUBDOMAIN="${NEXTCLOUD_SUBDOMAIN:-nextcloud}"
AK_SUBDOMAIN="${AUTHENTIK_SUBDOMAIN:-auth}"

NEXTCLOUD_URL="${NEXTCLOUD_PUBLIC_URL:-https://${NC_SUBDOMAIN}.${DOMAIN}}"
AUTHENTIK_URL="${AUTHENTIK_URL:-https://${AK_SUBDOMAIN}.${DOMAIN}}"
CLIENT_ID="${AUTHENTIK_NEXTCLOUD_CLIENT_ID:-authentik-nextcloud}"
CLIENT_SECRET="${AUTHENTIK_NEXTCLOUD_CLIENT_SECRET:-}"

if [[ -z "${CLIENT_SECRET}" ]]; then
  echo "AUTHENTIK_NEXTCLOUD_CLIENT_SECRET nao configurado" >&2
  exit 1
fi

occ() {
  docker exec -u www-data "${CONTAINER}" php occ "$@"
}

set_cfg() {
  local key="$1"
  local value="$2"
  occ config:system:set "${key}" --value="${value}"
}

install_app() {
  local app="$1"
  local out
  out=$(occ app:install "${app}" 2>&1) && { echo "App instalado: ${app}"; return 0; }
  if echo "${out}" | grep -qiE 'already installed|already enabled'; then
    echo "App ja presente: ${app}"
    return 0
  fi
  echo "AVISO: falha ao instalar ${app} — ${out}" >&2
  return 1
}

echo "[1/4] Instalando apps necessarios..."
install_app oidc_login
occ app:enable oidc_login
install_app groupfolders
occ app:enable groupfolders

echo "[2/4] Configurando URL automaticamente..."
set_cfg overwrite.cli.url "${NEXTCLOUD_URL}"
set_cfg overwriteprotocol "https"
occ config:system:set trusted_domains 1 --value="${NC_SUBDOMAIN}.${DOMAIN}" || true
# trusted_proxies: necessario para IP real do cliente (Cloudflare Tunnel / traefik)
occ config:system:set trusted_proxies 0 --value="127.0.0.1" || true
occ config:system:set trusted_proxies 1 --value="172.16.0.0/12" || true
# overwritehost: define hostname publico forcado quando o container recebe requests
# por nome interno diferente do publico (ex.: Cloudflare Tunnel)
if [[ -n "${NEXTCLOUD_OVERWRITE_HOST:-}" ]]; then
  set_cfg overwritehost "${NEXTCLOUD_OVERWRITE_HOST}"
  echo "overwritehost configurado: ${NEXTCLOUD_OVERWRITE_HOST}"
fi

echo "[3/4] Configurando OIDC Authentik..."
occ config:app:set oidc_login provider_url --value="${AUTHENTIK_URL}/application/o/nextcloud/"
occ config:app:set oidc_login client_id --value="${CLIENT_ID}"
occ config:app:set oidc_login client_secret --value="${CLIENT_SECRET}"
occ config:app:set oidc_login scope --value="openid profile email groups"
occ config:app:set oidc_login claim_groups --value="groups"
occ config:app:set oidc_login auto_provision --value="1"
occ config:app:set oidc_login soft_auto_provision --value="1"
occ config:app:set oidc_login hide_password_form --value="1"
occ config:app:set oidc_login use_id_token --value="1"

# Perfil do usuario sincronizado do Authentik
occ config:app:set oidc_login claim_mail --value="email"
occ config:app:set oidc_login claim_displayname --value="name"
occ config:app:set oidc_login claim_userid --value="preferred_username"

echo "[4/5] Aplicando baseline de seguranca por grupo..."
occ config:system:set sharing.manager_enforced_groups --value="1"
occ config:system:set profile.enabled --value="true"

echo "[5/6] Configurando redirecionamentos .well-known (CalDAV/CardDAV)..."
# A doc oficial recomenda que o reverse proxy (Cloudflare Tunnel / nginx / traefik)
# redirecione /.well-known/caldav e /.well-known/carddav para /remote.php/dav/.
# O Nextcloud nao faz esse redirect automaticamente quando esta atras de proxy.
# Esta configuracao garante que o overwrite.cli.url seja usado nas URLs geradas.
set_cfg htaccess.RewriteBase "/"
occ maintenance:update:htaccess || true

echo "[6/6] Instalando app rpa4all_admin_actions..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_SRC="${SCRIPT_DIR}/../apps/rpa4all_admin_actions"
docker cp "${APP_SRC}" "${CONTAINER}:/var/www/html/apps/"
docker exec "${CONTAINER}" chown -R www-data:www-data /var/www/html/apps/rpa4all_admin_actions
occ app:enable rpa4all_admin_actions

echo "Bootstrap concluido para ${CONTAINER}"
echo "Nextcloud: ${NEXTCLOUD_URL}"
echo "Authentik: ${AUTHENTIK_URL}"
