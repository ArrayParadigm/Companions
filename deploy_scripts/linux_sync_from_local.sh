#!/usr/bin/env bash
set -euo pipefail

# Repeatable Linux-side deployment sync.
# It copies the staged deploy package into the server path created by
# linux_setup_subdomain.sh, backs up the current server copy first, then
# restarts the service.

APP_USER="${APP_USER:-memorymanager}"
APP_DIR="${APP_DIR:-/opt/memorymanager}"
SERVICE_NAME="${SERVICE_NAME:-memorymanager}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/memorymanager_backups}"
SOURCE_DIR="${SOURCE_DIR:-/home/paradigm/memorymanager}"

PRESERVE_SERVER_DATA="${PRESERVE_SERVER_DATA:-1}"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this script with sudo/root."
    exit 1
  fi
}

install_tools() {
  if ! command -v rsync >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y rsync
  fi
}

validate_source() {
  if [[ ! -d "${SOURCE_DIR}" ]]; then
    echo "Source directory not found: ${SOURCE_DIR}"
    echo "Copy the deploy package contents into this folder, or override SOURCE_DIR."
    exit 1
  fi

  if [[ "$(readlink -f "${SOURCE_DIR}")" == "$(readlink -f "${APP_DIR}")" ]]; then
    echo "SOURCE_DIR and APP_DIR resolve to the same path. Refusing to sync onto itself."
    exit 1
  fi

  for required in Companion_Web.py Memory_Manager.py kjv.txt; do
    if [[ ! -f "${SOURCE_DIR}/${required}" ]]; then
      echo "Source is missing required file: ${required}"
      exit 1
    fi
  done
}

backup_current() {
  mkdir -p "${BACKUP_ROOT}"
  if [[ -d "${APP_DIR}" ]]; then
    local stamp
    stamp="$(date +%Y%m%d-%H%M%S)"
    tar -C "$(dirname "${APP_DIR}")" -czf "${BACKUP_ROOT}/memorymanager.${stamp}.tar.gz" "$(basename "${APP_DIR}")"
    echo "Server backup created: ${BACKUP_ROOT}/memorymanager.${stamp}.tar.gz"
  fi
}

sync_files() {
  mkdir -p "${APP_DIR}"

  local excludes=(
    --exclude '*-memories.md'
    --exclude '*_memories.md'
    --exclude 'template-memories.md'
    --exclude 'companion-files.json'
  )
  if [[ "${PRESERVE_SERVER_DATA}" == "1" ]]; then
    excludes+=(--exclude control_data --exclude proof_vault --exclude project_assets)
  fi

  rsync -a --delete "${excludes[@]}" "${SOURCE_DIR}/" "${APP_DIR}/"
  chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
  chmod +x "${APP_DIR}/run_web_console.sh" 2>/dev/null || true
}

validate_target() {
  for required in Companion_Web.py Memory_Manager.py kjv.txt; do
    if [[ ! -f "${APP_DIR}/${required}" ]]; then
      echo "Target is missing required file after sync: ${required}"
      exit 1
    fi
  done
}

restart_service() {
  systemctl restart "${SERVICE_NAME}.service"
  systemctl --no-pager --full status "${SERVICE_NAME}.service" || true
}

main() {
  require_root
  install_tools
  validate_source
  backup_current
  sync_files
  validate_target
  restart_service

  echo
  echo "Sync complete."
  echo "Source: ${SOURCE_DIR}"
  echo "Target: ${APP_DIR}"
}

main "$@"
