#!/usr/bin/env bash
# Local/test self-signed server certificate; use a CA-issued certificate when available.
set -Eeuo pipefail
umask 077
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ $# -gt 0 ]] || { echo 'Usage: bash scripts/create-cert.sh HOSTNAME_OR_IP [ADDITIONAL_NAMES_OR_IPS...]' >&2; exit 2; }
command -v openssl >/dev/null || { echo 'Install OpenSSL first.' >&2; exit 1; }
[[ ! -e certs/server.key && ! -e certs/server.crt ]] || { echo 'Certificate/key already exists. Back it up and move it before intentionally generating a replacement.' >&2; exit 1; }
mkdir -p certs
config="$(mktemp)";work="$(mktemp -d)"
trap 'rm -f "$config"; rm -rf "$work"' EXIT
printf '%s\n' '[req]' 'prompt = no' 'distinguished_name = dn' 'x509_extensions = ext' '[dn]' 'CN = MEOSAR Scheduler' '[ext]' 'basicConstraints = critical,CA:FALSE' 'keyUsage = critical,digitalSignature,keyEncipherment' 'extendedKeyUsage = serverAuth' 'subjectAltName = @names' '[names]' 'DNS.1 = localhost' 'IP.1 = 127.0.0.1' 'IP.2 = ::1' > "$config"
dns=1;ip=2
for name in "$@"; do
    [[ ${#name} -le 253 && "$name" =~ ^[a-zA-Z0-9][a-zA-Z0-9.:-]*$ ]] || { echo "Invalid DNS name or IP: $name" >&2; exit 2; }
    if [[ "$name" == *:* || "$name" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        ip=$((ip+1));printf 'IP.%s = %s\n' "$ip" "$name" >> "$config"
    else
        dns=$((dns+1));printf 'DNS.%s = %s\n' "$dns" "$name" >> "$config"
    fi
done
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 -config "$config" -keyout "$work/server.key" -out "$work/server.crt" >/dev/null 2>&1
chmod 600 "$work/server.key";chmod 644 "$work/server.crt"
mv "$work/server.key" certs/server.key;mv "$work/server.crt" certs/server.crt
printf '%s\n' 'Created certs/server.crt and certs/server.key (valid for 365 days).' 'This is self-signed. Clients must trust the certificate through your approved process.' 'Do not commit, email, or share server.key. Generate a server-specific certificate on the server.'
openssl x509 -in certs/server.crt -noout -dates -fingerprint -sha256
