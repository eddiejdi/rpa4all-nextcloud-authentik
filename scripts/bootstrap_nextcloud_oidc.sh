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

echo "[1/4] Instalando apps necessarios..."
occ app:install oidc_login || true
occ app:enable oidc_login
occ app:install groupfolders || true
occ app:enable groupfolders

echo "[2/4] Configurando URL automaticamente..."
set_cfg overwrite.cli.url "${NEXTCLOUD_URL}"
set_cfg overwriteprotocol "https"
occ config:system:set trusted_domains 1 --value="${NC_SUBDOMAIN}.${DOMAIN}" || true

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

echo "[4/4] Aplicando baseline de seguranca por grupo..."
occ config:system:set sharing.manager_enforced_groups --value="1"
occ config:system:set profile.enabled --value="true"

echo "Bootstrap concluido para ${CONTAINER}"
echo "Nextcloud: ${NEXTCLOUD_URL}"
echo "Authentik: ${AUTHENTIK_URL}"
