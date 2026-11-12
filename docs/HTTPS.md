# HTTPS and certificates

MEOSAR can use the same arrangement as the Network Monitor deployment:

```text
Browser: https://SERVER_NAME:4443
        |
        v
nginx: certificate + private key, TLS 1.2/1.3
        |
        v
MEOSAR web:8080 (private Compose network, no published backend port)
```

This uses `compose.yaml` plus `compose.https.yaml`. It requires Docker Compose
2.24.4 or newer. The optional nginx image is `nginx:stable-alpine`; an engineer
can pin an approved image digest with MEOSAR_NGINX_IMAGE.

## Why 4443 instead of 443?

The coworker's Compose file publishes host ports 80 and 443. Two containers
cannot bind the same address and port simultaneously. MEOSAR defaults to 4443
so both applications can coexist. The engineer can choose another available
port, or route separate DNS names through one shared reverse proxy on 443.
Do not stop or reconfigure the coworker's app to free its ports.

## Supply a certificate and key

The expected files are:

```text
certs/
  server.crt   # PEM server certificate, with intermediates if applicable
  server.key   # matching PEM private key
```

Use either an engineer-provided internal-CA certificate, or a self-signed server
certificate for an explicitly approved deployment/test. An internal CA signs
certificates that managed computers may already trust. A self-signed server
certificate needs an approved client trust setup; encryption alone does not
make an unknown certificate trusted by browsers.

**The certificate must list the actual DNS name/IP users open in its Subject
Alternative Names.** A localhost test certificate does not identify the Ubuntu
server. Do not reuse the coworker's private key or copy it out of their repo.

Certificate/key files are ignored by Git and excluded from the app image build.
Mount the certificate directory read-only at runtime. Keep the private key 0600
and restrict the directory; the nginx root master reads it and starts ordinary
unprivileged workers. The MEOSAR application continues running as UID 10001.
Never commit or post a private key, including in this public repository.

### Generate a self-signed certificate

On the machine where the certificate will be used, with OpenSSL installed:

```bash
# Local Mac test only:
bash scripts/create-cert.sh localhost

# On Ubuntu: replace these examples with the engineer-approved name/IP:
bash scripts/create-cert.sh meosar.internal.example 192.168.1.50
```

Choose one command for that machine. The script refuses to overwrite an existing
certificate/key. It creates a 3072-bit RSA certificate valid for 365 days with
SANs for the supplied names/IPs and local loopback. It does not install trust,
open firewall ports or enable HTTPS by itself. For server deployment, generate
the key on the server or use the organization's certificate issuance process.

## Ubuntu startup

Copy `ubuntu.env.example` to `ubuntu.env` if not already present. Set:

```dotenv
MEOSAR_BIND_ADDRESS=SERVER_LAN_IP
MEOSAR_HTTPS=1
MEOSAR_HTTPS_PORT=4443
# Optional absolute directory instead of ./certs:
# MEOSAR_CERT_DIRECTORY=/srv/meosar/certs
```

SERVER_LAN_IP is a placeholder to replace with the real bind address. The helper
reads the unquoted `MEOSAR_HTTPS=1` setting and selects both Compose files for
startup, status, updates, backups and logs:

```bash
bash scripts/server.sh start
bash scripts/server.sh status
```

Open `https://THE_NAME_OR_IP_ON_THE_CERTIFICATE:4443`.
The Ubuntu example enables HTTPS; supply the certificate/key before startup.
In this mode, MEOSAR_PORT is unused and port 8080 is not published. Only nginx's
HTTPS endpoint is published. Ports 80/443 are not claimed and HTTP redirects are
not provided by this standalone setup.

Keep MEOSAR_HTTPS=1 for future updates:

```bash
git pull --ff-only origin main
bash scripts/server.sh update
```

The same data volume is reused when switching between HTTP and HTTPS; it does
not copy, delete or replace saved missions. Wait for jobs/video exports to finish
before switching modes. The update helper backup briefly pauses the web service.

## Local HTTPS test

Plain `docker compose up -d` is HTTP-only unless a local .env sets
`COMPOSE_FILE=compose.yaml:compose.https.yaml`. With that setting, ordinary Compose
commands remember HTTPS. Keep local .env settings out of Git. To switch
that same local stack to HTTPS, after supplying the localhost certificate:

```bash
docker compose -f compose.yaml -f compose.https.yaml up -d --wait
```

Open `https://localhost:4443`. This replaces the local HTTP port publication;
it does not start a second app/data volume. To return deliberately to HTTP:

```bash
docker compose -f compose.yaml -f compose.https.yaml stop https
docker compose -f compose.yaml up -d --remove-orphans --wait
```

Both modes retain the same data volume. Do not use `down -v` to switch modes.
Browser trust configuration should follow the engineer's process. Do not treat
clicking past a certificate warning as a permanent deployment solution.

To verify a self-signed localhost certificate without disabling verification:

```bash
curl --cacert certs/server.crt https://localhost:4443/healthz
```

For an internal CA, use the approved CA trust bundle rather than assuming the
server's leaf certificate is the appropriate CA file.

## Certificate replacement

Track certificate expiration. Replace the certificate and matching key in the
mounted directory through your approved process, then validate and reload nginx:

```bash
docker compose --env-file ubuntu.env -f compose.yaml -f compose.https.yaml exec https nginx -t
docker compose --env-file ubuntu.env -f compose.yaml -f compose.https.yaml exec https nginx -s reload
```

No application rebuild is needed. The script does not automatically renew
certificates or distribute trust to browsers. Never replace a certificate for a
changed hostname without coordinating DNS/client access.

## Notes for a shared server reverse proxy

If engineering prefers an existing shared proxy, it can provide the certificate
and routing instead of this bundled nginx service. Keep backend access limited
to that trusted proxy, forward the original Host including non-default port,
set X-Forwarded-Proto, and configure trusted forwarded headers appropriately.
The app checks same-origin writes, including video frames; test a real write and
video export through HTTPS, not just a GET of the homepage.

The bundled mode trusts forwarded headers because the backend has no published
host port and nginx replaces those headers on the dedicated project network.
Do not expose that backend directly while retaining wildcard proxy trust.
Use a dedicated hostname at the URL root; subpath hosting needs separate work.

HTTPS protects transport. It does not add application logins, roles or person-level
auditing. Network access restrictions and the existing shared-access decision
still apply.
