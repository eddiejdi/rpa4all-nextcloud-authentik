#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${NEXTCLOUD_CONTAINER:-nextcloud-rpa4all}"
SVG_FILE="${1:-}"
BG_COLOR="${NEXTCLOUD_BG_COLOR:-#0A1830}"

if [[ -z "${SVG_FILE}" ]]; then
  echo "Uso: $0 /caminho/background.svg" >&2
  exit 1
fi

if [[ ! -f "${SVG_FILE}" ]]; then
  echo "Arquivo nao encontrado: ${SVG_FILE}" >&2
  exit 1
fi

echo "[1/3] Copiando SVG para o container ${CONTAINER}..."
docker cp "${SVG_FILE}" "${CONTAINER}:/tmp/rpa4all-background.svg"

echo "[2/3] Aplicando fundo global via API interna do Theming..."
docker exec -i -u www-data "${CONTAINER}" php <<'PHP'
<?php
require '/var/www/html/lib/base.php';

$source = '/tmp/rpa4all-background.svg';
if (!is_readable($source)) {
	fwrite(STDERR, "Nao foi possivel ler " . $source . PHP_EOL);
	exit(1);
}

$imageManager = \OC::$server->query(\OCA\Theming\ImageManager::class);
$themingDefaults = \OC::$server->query(\OCA\Theming\ThemingDefaults::class);

$mime = $imageManager->updateImage('background', $source);
$themingDefaults->set('backgroundMime', $mime);

echo "backgroundMime aplicado: " . $mime . PHP_EOL;
PHP

echo "[3/3] Ajustando cor de fallback e atualizando assets de tema..."
docker exec -u www-data "${CONTAINER}" php occ theming:config background_color "${BG_COLOR}"
docker exec -u www-data "${CONTAINER}" php occ maintenance:theme:update || true
docker exec -u www-data "${CONTAINER}" php occ theming:config

echo "Fundo aplicado com sucesso."
