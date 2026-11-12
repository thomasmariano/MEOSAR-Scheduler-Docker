# Git → Ubuntu LAN deployment

This repository contains the standalone browser app. The desktop app remains in MEOSAR-Scheduler. Ubuntu builds the web
container from source for its own amd64 or arm64 processor. No Mac app bundle,
ZIP export, Python environment, or client-side installation is needed.

The planned Ubuntu installation is a **fresh installation**. Transfer the source
through GitHub, not the Mac's runtime data. Default location/satellite/antenna
libraries are bundled; import/download TLEs and create announcements/calendar
events on Ubuntu. The backup/restore section is for later recovery or an optional
migration, not a requirement for this first deployment.

## 1. Publish the tested source from your Mac

From the project root:

```bash
git status --short
git diff --stat
git add .
git diff --cached --stat
git commit -m "Prepare MEOSAR web 2.0.3 for Ubuntu deployment"
git push origin main
```

Review the staged file list before committing. Include Dockerfile, compose.yaml,
.dockerignore, both requirements-web files, scripts/server.sh, ubuntu.env.example,
web/, simulation browser assets, shared Python modules and the deployment docs.
The three config library JSON files are first-run defaults: check that their
contents are appropriate for the server. Do not include credentials, local env
files, .venv, build/dist, backup archives or runtime mission/TLE data.

Git uploads code and bundled defaults, not the running Mac Docker data volume.
The server starts with its own libraries, jobs, calendar and announcements.
To transfer existing browser data, use the backup/restore section below instead.

## 2. Install Docker on Ubuntu

Install Docker Engine and the Compose plugin using the official instructions:
https://docs.docker.com/engine/install/ubuntu/

Verify the account used for deployment can run:

```bash
docker version
docker compose version
git --version
```

Docker documents how to configure account access after installation. Use an
account permitted to operate Docker; do not switch casually between sudo and
non-sudo commands, which can leave root-owned files in the checkout.

The server needs outbound access to GitHub and Docker/package repositories for
this source-build workflow, and to CelesTrak/Space-Track for online TLE retrieval.
Local file and mounted-folder imports remain usable without those TLE sites.
If the server cannot reach those repositories, use an architecture-matched image
transfer workflow instead; cloning alone cannot supply missing image/packages.

## 3. First install on the server

The Ubuntu env example enables nginx HTTPS. Follow [HTTPS.md](HTTPS.md) to supply
`certs/server.crt` and `certs/server.key` before starting. Default HTTPS is 4443
to avoid another application already using 443; the backend port stays private.


Run these on Ubuntu, not on the Mac:

```bash
mkdir -p ~/apps
cd ~/apps
git clone https://github.com/thomasmariano/MEOSAR-Scheduler-Docker.git
cd MEOSAR-Scheduler-Docker
cp ubuntu.env.example ubuntu.env
nano ubuntu.env
```

For a private repository, configure the server's GitHub access first, preferably
a read-only repository deploy key. Do not place a token in the repository URL
or commit it to an env/config file.

Set MEOSAR_BIND_ADDRESS to the server LAN IP, such as 192.168.1.50, or use
0.0.0.0 to listen on all interfaces. Set MEOSAR_HTTPS=1 and choose an available MEOSAR_HTTPS_PORT (default 4443).
MEOSAR_PORT applies only to HTTP-only mode. ubuntu.env is ignored by Git and survives pulls.
The default TLE-import folder is ./tle-imports; set MEOSAR_TLE_IMPORT_DIR to
an absolute host directory if needed. That folder is mounted read-only.

```bash
bash scripts/server.sh start
bash scripts/server.sh status
```

The helper builds the image, starts the service, waits for Docker's health
check and records the deployed Git commit in ignored .deployment/ files.
The first build takes longer while dependencies and FFmpeg download.

On any computer on the same network, open:

```text
https://SERVER_NAME_ON_CERTIFICATE:4443
```

There is no application login, as requested. Everyone with network access can
modify the shared application data. Restrict the published port to the intended
LAN using the server/network configuration. Docker-published ports can bypass
ordinary UFW rules; follow Docker's documented firewall guidance:
https://docs.docker.com/engine/install/ubuntu/#firewall-limitations

## 4. Test the server before using it operationally

- Open it from a second computer, not just the server.
- Import TLEs, generate a short representative schedule and compare it with
  the same inputs/TLEs on the Mac.
- Save a mission, edit a pass, reopen its simulator and test a short video.
- Publish a test announcement and check the other browser within 15 seconds.
- Run `bash scripts/server.sh start` again, then verify the saved data remains.
- Run `bash scripts/server.sh backup` and retain a copy off the server.

The Docker named volume holds runtime data independently of Git and the
container: libraries, TLEs, jobs, saved schedules, presets/events, announcements,
monitoring locations and video files. Browser-local preferences/unread state
are stored in that browser, not in the server backup. Video rendering still
requires the exporting browser tab to remain open.

## 5. Routine updates

On the Mac: test, commit and push the intended changes:

```bash
git status --short
git add .
git diff --cached --stat
git commit -m "Describe the update"
git push origin main
```

On Ubuntu, wait for calculations and video exports to finish, then:

```bash
cd ~/apps/MEOSAR-Scheduler-Docker
git pull --ff-only origin main
bash scripts/server.sh update
```

The update helper refuses a dirty checkout, creates a consistent backup while
the service is briefly stopped, restarts the existing service, then builds and
recreates it with the updated code and waits for health. It records the new
commit only after successful startup. Existing data stays in the same volume.
Bundled config defaults only seed missing server libraries; a Git pull does not overwrite existing server library edits. Use the web library editors to add, edit or remove individual records. Whole-library JSON replacement is disabled; TLE imports remain available. Announcements posted on the Mac are also local to its Docker data, not shipped through Git.

Users should hard-refresh after an update. Expect short downtime; the app has a single web service behind nginx, not a zero-downtime rollout.

No webhook or automatic pull is required. A GitHub push does not change the
server until someone runs these server commands. This keeps deployment timing
under your control. For a more controlled release, deploy a tested tag/commit
instead of the newest main commit.

```bash
bash scripts/server.sh status
bash scripts/server.sh logs
cat .deployment/deployed-commit
cat .deployment/previous-commit
```

If startup fails, inspect logs. The previous commit and pre-update backup are
available for recovery. Code rollback is a deliberate checkout/rebuild; a data
format change may also require restoring a matching backup. The helper never
automatically rolls back or restores data over the live volume.

Python dependencies in requirements-web.lock.txt match the tested development
container. requirements-web.txt describes direct dependencies. When intentionally
upgrading packages, regenerate/review the lock from a tested container and
commit it too. Base-image and Ubuntu system packages are not pinned by that lock.

## 6. Backup and restore test

```bash
bash scripts/server.sh backup
```

Archives are timestamped under ignored backups/. The helper stops the writer,
archives /data, verifies the gzip/tar listing, and restarts the service if it
was running. Failed backup attempts stop an update. Copy archives to a separate
backup destination; a same-disk backup does not protect against disk failure.
The host TLE-import directory needs its own backup if its originals matter.
Backups contain application/mission information; keep access restricted.

To restore a trusted backup for testing, use a NEW Compose project and port.
Replace the archive name below with the real timestamped filename:

```bash
docker compose -p meosar-web-restore --env-file ubuntu.env run --rm --no-deps -T web python -c \
  'import sys,tarfile; a=tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz"); a.extractall("/data",filter="data"); a.close()' \
  < backups/REPLACE_WITH_BACKUP.tar.gz
MEOSAR_BIND_ADDRESS=127.0.0.1 MEOSAR_PORT=8081 docker compose -p meosar-web-restore --env-file ubuntu.env up -d --no-build --wait
```

This manual restore test intentionally uses HTTP on server loopback only. Check
http://127.0.0.1:8081 on the server, or use an approved SSH tunnel. This uses a separate
volume and does not overwrite the live application. A Mac-browser-data transfer
can use the same /data archive format, restoring into a fresh server volume
before first operational use. Do not overwrite existing server data casually.

Keep the main Compose project name `meosar-web` and the same checkout/env settings
for ordinary updates. Changing project names selects a different data volume.
**Do not run `docker compose down -v` on the live deployment:** it deletes its
persistent volume. Git pulls and normal container rebuilds do not delete it.

## Local Mac use

Continue using the existing localhost configuration:

```bash
docker compose up -d --build
```

The Ubuntu helper expects ubuntu.env deliberately; do not use the LAN env file
on the Mac unless that exposure is intended. Local and server Docker volumes
remain independent. No Git push, remote deployment or live data restore has
been performed by preparing these files.
