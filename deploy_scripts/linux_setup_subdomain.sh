#!/usr/bin/env bash
set -euo pipefail

# First-time server setup for the Companion Control Console.
# Tested target style: Debian/Ubuntu with Apache2, systemd, certbot.
#
# DNS note:
# This script configures the Linux server for the subdomain. It cannot create
# the DNS record at GoDaddy without API credentials. Create an A/AAAA record
# for DOMAIN before running certbot.

DOMAIN="${DOMAIN:-companions.paradigmlabs.dev}"
APP_USER="${APP_USER:-memorymanager}"
APP_DIR="${APP_DIR:-/opt/memorymanager}"
APP_PORT="${APP_PORT:-8787}"
SERVICE_NAME="${SERVICE_NAME:-memorymanager}"
APACHE_SITE="${APACHE_SITE:-memorymanager}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
ACME_ROOT="${ACME_ROOT:-/var/www/letsencrypt}"
REQUIRE_BASIC_AUTH="${REQUIRE_BASIC_AUTH:-0}"
BASIC_AUTH_USER="${BASIC_AUTH_USER:-array}"
BASIC_AUTH_FILE="${BASIC_AUTH_FILE:-/etc/apache2/.htpasswd-memorymanager}"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this script with sudo/root."
    exit 1
  fi
}

install_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y python3 python3-tk apache2 certbot apache2-utils dnsutils rsync
}

create_user_and_dirs() {
  if ! id "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
  fi

  mkdir -p "${APP_DIR}" "${APP_DIR}/app_data" "${APP_DIR}/control_data" "${APP_DIR}/proof_vault" "${APP_DIR}/project_assets"
  mkdir -p "${ACME_ROOT}/.well-known/acme-challenge"
  chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
  chown -R www-data:www-data "${ACME_ROOT}"
}

configure_basic_auth() {
  if [[ "${REQUIRE_BASIC_AUTH}" != "1" ]]; then
    return
  fi

  if [[ -z "${BASIC_AUTH_PASSWORD:-}" ]]; then
    read -r -s -p "Basic auth password for ${BASIC_AUTH_USER}: " BASIC_AUTH_PASSWORD
    echo
  fi

  htpasswd -bc "${BASIC_AUTH_FILE}" "${BASIC_AUTH_USER}" "${BASIC_AUTH_PASSWORD}"
  chmod 640 "${BASIC_AUTH_FILE}"
  chown root:www-data "${BASIC_AUTH_FILE}"
}

write_systemd_service() {
  cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Companion Control Console
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/python3 ${APP_DIR}/Companion_Web.py --host 127.0.0.1 --port ${APP_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}.service"
}

auth_block() {
  if [[ "${REQUIRE_BASIC_AUTH}" != "1" ]]; then
    return
  fi

  cat <<EOF
        AuthType Basic
        AuthName "Companion Control Console"
        AuthUserFile ${BASIC_AUTH_FILE}
        Require valid-user
EOF
}

write_apache_http_site() {
  local auth_block=""
  auth_block="$(auth_block)"

  a2enmod proxy proxy_http headers rewrite ssl >/dev/null

  cat > "/etc/apache2/sites-available/${APACHE_SITE}.conf" <<EOF
<VirtualHost *:80>
    ServerName ${DOMAIN}

    Alias /.well-known/acme-challenge/ ${ACME_ROOT}/.well-known/acme-challenge/
    <Directory "${ACME_ROOT}/.well-known/acme-challenge/">
        Options None
        AllowOverride None
        Require all granted
    </Directory>

    ProxyPreserveHost On
    ProxyRequests Off
    ProxyPass /.well-known/acme-challenge/ !
    ProxyPass / http://127.0.0.1:${APP_PORT}/
    ProxyPassReverse / http://127.0.0.1:${APP_PORT}/

    LimitRequestBody 52428800

    <Location />
${auth_block}
    </Location>

    <Location "/.well-known/acme-challenge/">
        AuthType None
        Require all granted
    </Location>

    RequestHeader set X-Forwarded-Proto "http"
    ErrorLog \${APACHE_LOG_DIR}/${APACHE_SITE}_error.log
    CustomLog \${APACHE_LOG_DIR}/${APACHE_SITE}_access.log combined
</VirtualHost>
EOF

  a2ensite "${APACHE_SITE}.conf" >/dev/null
  apache2ctl configtest
  systemctl reload apache2
}

write_apache_https_site() {
  local auth_block=""
  auth_block="$(auth_block)"

  cat > "/etc/apache2/sites-available/${APACHE_SITE}.conf" <<EOF
<VirtualHost *:80>
    ServerName ${DOMAIN}

    Alias /.well-known/acme-challenge/ ${ACME_ROOT}/.well-known/acme-challenge/
    <Directory "${ACME_ROOT}/.well-known/acme-challenge/">
        Options None
        AllowOverride None
        Require all granted
    </Directory>

    RewriteEngine On
    RewriteCond %{REQUEST_URI} !^/\\.well-known/acme-challenge/
    RewriteRule ^/(.*)$ https://%{HTTP_HOST}/\$1 [R=301,L]

    ErrorLog \${APACHE_LOG_DIR}/${APACHE_SITE}_error.log
    CustomLog \${APACHE_LOG_DIR}/${APACHE_SITE}_access.log combined
</VirtualHost>

<IfModule mod_ssl.c>
<VirtualHost *:443>
    ServerName ${DOMAIN}

    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/${DOMAIN}/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/${DOMAIN}/privkey.pem

    ProxyPreserveHost On
    ProxyRequests Off
    ProxyPass /.well-known/acme-challenge/ !
    ProxyPass / http://127.0.0.1:${APP_PORT}/
    ProxyPassReverse / http://127.0.0.1:${APP_PORT}/
    LimitRequestBody 52428800

    <Location />
${auth_block}
    </Location>

    <Location "/.well-known/acme-challenge/">
        AuthType None
        Require all granted
    </Location>

    RequestHeader set X-Forwarded-Proto "https"
    ErrorLog \${APACHE_LOG_DIR}/${APACHE_SITE}_ssl_error.log
    CustomLog \${APACHE_LOG_DIR}/${APACHE_SITE}_ssl_access.log combined
</VirtualHost>
</IfModule>
EOF

  apache2ctl configtest
  systemctl reload apache2
}

check_dns() {
  if ! dig +short "${DOMAIN}" | grep -qE '^[0-9a-fA-F:.]+$'; then
    echo "DNS for ${DOMAIN} does not resolve yet."
    echo "Create the DNS record first, then rerun this script for certbot."
    return 1
  fi
  return 0
}

run_certbot() {
  if ! check_dns; then
    return
  fi

  if [[ -z "${CERTBOT_EMAIL}" ]]; then
    read -r -p "Certbot email for Let's Encrypt notices: " CERTBOT_EMAIL
  fi

  certbot certonly --webroot \
    --non-interactive \
    --agree-tos \
    --email "${CERTBOT_EMAIL}" \
    -w "${ACME_ROOT}" \
    -d "${DOMAIN}"

  write_apache_https_site
}

main() {
  require_root
  install_packages
  create_user_and_dirs
  configure_basic_auth
  write_systemd_service
  write_apache_http_site
  systemctl restart "${SERVICE_NAME}.service" || true
  run_certbot

  echo
  echo "Server setup complete."
  echo "App directory: ${APP_DIR}"
  echo "Service: ${SERVICE_NAME}.service"
  echo "Apache site: /etc/apache2/sites-available/${APACHE_SITE}.conf"
  echo "URL: https://${DOMAIN}"
  echo
  echo "Next: copy the deploy package into /home/paradigm/memorymanager, then run linux_sync_from_local.sh."
}

main "$@"
