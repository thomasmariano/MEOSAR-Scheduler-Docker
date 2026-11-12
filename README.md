# MEOSAR Scheduler Docker

**Developed and maintained by Thomas Mariano.**

**Current application version: 2.0.3**

A self-hosted browser application for MEOSAR mission planning, satellite
visibility analysis, antenna scheduling, schedule editing, and satellite
simulation. Users access one shared installation on an internal network instead
of installing the desktop application on each computer.

This repository is **standalone**: it includes the web interface, calculation
modules, simulator assets, FFmpeg installation, and Docker configuration. It
does not require the [separate desktop repository](https://github.com/thomasmariano/MEOSAR-Scheduler)
to build or run. The desktop and web versions are maintained separately.

## Features

- UTC mission event day/time and tracking windows before and after the event.
- Mutual satellite visibility between a receiving ground station and mission site.
- Antenna-compatible scheduling, angular separation, and ordered alternate-site preferences.
- Interactive assignment timeline, coverage-based pass additions, validated edits,
  saved revisions, coverage graphs, and schedule diagnostics.
- Saved missions, previous jobs, and a shared launch/landing calendar.
- Saved satellite, antenna, and location libraries with individual add/edit/delete controls.
- TLE retrieval from CelesTrak and Space-Track, local file/folder uploads,
  mounted server-folder imports, automatic epoch selection, and epoch review.
- Shared announcements and antenna availability updates for future calculations.
- Browser globe simulation, orbit/ground tracks, monitoring locations, and coverage displays.
- Video export with camera controls and selectable information panels.
- Schedule TXT exports, ZIP packages for simulation replay, graph downloads,
  and an optional host-accessible files library.
- Light/dark themes and customizable simulator dashboards.

Whole-library JSON uploads are disabled. Use **Manage libraries** to update
individual saved entries. TLE imports remain available.

## Architecture

```text
Network users: https://SERVER-NAME:4443
                    |
                    v
             nginx HTTPS proxy
                    |
                    v
       Python / FastAPI web application
       Scheduling, propagation, graph generation
                    |
                    v
      Persistent Docker volume or server folders
```

In the supplied HTTPS configuration, **only port 4443 is published**. The app's
port 8080 stays on the private Compose network. Ports 80 and 443 are not required;
this setup does not redirect HTTP to HTTPS.

The server performs scheduling, propagation, graph generation, and FFmpeg video
encoding. The browser renders the interactive simulator and supplies video
frames. **Keep the exporting browser tab open until video export finishes.**

The web container does not require PyQt6. The Dockerfile is intended for native
Linux **amd64 and arm64** builds without changing the source. Deployment on the
target Ubuntu server still needs to be tested; local Mac testing alone does not
establish Ubuntu compatibility or operational acceptance of the calculations.

## Intended deployment

- Internal Ubuntu server; the planned target is Ubuntu 22.04.5 LTS.
- Docker Engine and the Docker Compose plugin **2.24.4 or newer**.
- HTTPS on **4443**, with a certificate matching the server hostname/IP.
- Shared access without application logins, by design.
- Persistent server storage for saved work and imported/downloaded TLEs.

Everyone who can reach the app can modify shared libraries, missions and notices.
Restrict access to the intended network/users. HTTPS encrypts traffic; it does
not add accounts or permissions. Your engineer should check Docker-aware firewall
rules: see [Docker's firewall documentation](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

The server needs outbound access to GitHub and the image/package repositories
used during builds (Docker registries, Debian package repositories, and PyPI).
Online TLE retrieval additionally needs access to CelesTrak and Space-Track.
Local TLE uploads can be used without reaching those TLE providers. A restricted
or offline build requires a separately prepared image/dependency transfer.

## Fresh installation on Ubuntu

**No Mac runtime data needs to be transferred for this deployment.** The server
starts with the three bundled default resource libraries. Its TLE library,
mission/job history, calendar and announcements start empty and can be populated
on the server. Review `config/locations.json`, `config/satellites.json` and
`config/antennas.json` before publishing them as defaults in this public repository.

### 1. Check prerequisites and clone

Install Docker Engine and the Compose plugin using the
[official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
The deployment account must be permitted to run Docker.

```bash
docker version
docker compose version
git --version

git clone https://github.com/thomasmariano/MEOSAR-Scheduler-Docker.git
cd MEOSAR-Scheduler-Docker
cp ubuntu.env.example ubuntu.env
nano ubuntu.env
```

In `ubuntu.env`, set the real server bind address. For example:

```dotenv
# Replace this example with the server's actual LAN IP.
MEOSAR_BIND_ADDRESS=192.168.1.50
MEOSAR_HTTPS=1
MEOSAR_HTTPS_PORT=4443
```

The supplied example uses `0.0.0.0` to listen on all server interfaces; use a
specific LAN address if required by engineering. `MEOSAR_PORT` applies only to
HTTP mode and is unused with HTTPS enabled. Keep the env-file settings unquoted
as shown in `ubuntu.env.example` when using the helper script.

### 2. Supply the server certificate

On Ubuntu, provide these files through your engineer's certificate process:

```text
certs/server.crt
certs/server.key
```

The certificate must cover the **actual hostname/IP users will open**. The Mac's
localhost certificate is not suitable for that server address. An internal-CA
certificate is supported; self-signed certificates require an approved client
trust setup. Keep the private key restricted and out of GitHub.

For a self-signed certificate generated on the server, see the exact commands
and restrictions in [HTTPS setup](docs/HTTPS.md). Do not generate a new certificate
over an engineer-provided one.

### 3. Choose storage before first startup

**Default:** leave `MEOSAR_FILES_DIRECTORY` unset. Docker keeps application data
in a persistent named volume; browser schedule/graph/video downloads still work.

**Optional accessible folders:** to browse published files directly on the server,
create the folder layout and set its owner IDs as described in
[file storage](docs/FILE_STORAGE.md). Then configure `MEOSAR_FILES_DIRECTORY`,
`MEOSAR_UID`, and `MEOSAR_GID` in `ubuntu.env` **before starting**. The helper
selects the folder overlay automatically.

```text
MEOSAR Files/
  Application Data/     canonical application data; do not edit manually
  Exports/              readable schedules, graphs and videos
  TLE Library/          readable copies of TLE sources
  TLE Imports/          files to import through the browser
```

The folder lives on the **server**. Browser downloads save copies to the user's
computer, normally Downloads. Direct folder access from other computers requires
a separately configured network share. Do not broadly share Application Data or
certificate/private-key directories.

### 4. Build and start

```bash
bash scripts/server.sh start
bash scripts/server.sh status
```

The first build downloads the base image, Python packages, and FFmpeg. The helper
waits for container health and records the deployed Git commit. Once healthy, open:

```text
https://THE-SERVER-NAME-ON-THE-CERTIFICATE:4443
```

Users need a browser and network access; no local Python or FFmpeg installation
is required. Use a dedicated hostname at the URL root; hosting under a subpath
such as `/meosar/` requires additional configuration.

### 5. Check the installation

From another computer on the intended network:

1. Confirm HTTPS works through the approved certificate trust setup.
2. Review resource libraries and import/download TLEs.
3. Generate a representative schedule and compare it with the same inputs/TLEs
   used in local testing.
4. Edit a pass, save/reopen the mission, and download its schedule package.
5. Load the simulator and export a short video.
6. Post a test announcement and verify it appears in another browser.
7. Check that saved work survives a container restart and test a backup/restore
   in a separate instance before operational use.

Full setup and recovery instructions: [Ubuntu deployment guide](docs/UBUNTU_LAN_DEPLOYMENT.md).

## Updating from the Mac through GitHub

On the development computer: make changes, test locally, review the files, then
commit and push them to this repository. A GitHub push **does not automatically
update the server**.

On Ubuntu, after active calculations and video exports finish:

```bash
cd /path/to/MEOSAR-Scheduler-Docker
git pull --ff-only origin main
bash scripts/server.sh update
```

Replace the path with the actual checkout. The helper requires a clean Git
checkout, backs up `/data`, rebuilds/restarts the app, and waits for healthy
containers. Expect brief downtime. Existing server library edits and saved work
remain in persistent storage; updated bundled defaults do not replace them.
Use a tested tag/commit when a controlled release is needed. Users should
hard-refresh their browsers after an update.

`ubuntu.env`, certificates and runtime data stay on the server and are not
synchronized through Git. Keep the same Compose project (`meosar-web`), env file
and storage settings across updates to avoid selecting a different data store.

## Administration and backups

```bash
bash scripts/server.sh status
bash scripts/server.sh logs
bash scripts/server.sh backup
cat .deployment/deployed-commit
```

Backups are timestamped under ignored `backups/`. The helper briefly stops the
writer, archives `/data`, checks the archive listing, and restarts the service
if it was running. Keep backup copies off the server and test restoration.

The `/data` backup covers canonical jobs, saved schedules/revisions, libraries,
TLEs, calendar, announcements and completed videos. Back up the server env file,
certificates/private key and original TLE-import files separately as appropriate.
Published Exports/TLE Library files are regenerable copies. Browser preferences
and notification read status are local to each browser.

**Do not use `docker compose down -v` on the live named-volume installation:**
it removes its persistent data volume. Clearing previous jobs hides them from
history; it does not reclaim their stored files. Plan disk capacity and retention,
especially for videos. Code rollback and data restore are deliberate operations;
the update helper does not perform automatic rollback.

## Local development

For a separate local HTTP-only test:

```bash
cp .env.example .env
docker compose up -d --build
```

Open `http://localhost:8081`. Do not overwrite an existing local `.env`; it may
already select HTTPS and host-folder storage. The current Mac development stack
uses `https://localhost:4443`. See [HTTPS setup](docs/HTTPS.md) for local overlays.
Local test data does not travel to Ubuntu when code is pushed.

## Before wider use

Target-server testing, performance/capacity planning, backup retention, certificate
renewal, dependency/container security review, and operational validation remain
part of deployment acceptance. There are no application accounts, permission
roles, person-level audit trail, email/push announcements, or automatic deployments.
The app runs as a non-root user with reduced Linux capabilities and bounded jobs;
those measures are not a substitute for a security review.

## Documentation

- [Ubuntu deployment and updates](docs/UBUNTU_LAN_DEPLOYMENT.md)
- [HTTPS and certificates](docs/HTTPS.md)
- [File storage and downloads](docs/FILE_STORAGE.md)
- [Repository workflow](docs/REPOSITORY_WORKFLOW.md)
- [Desktop/web feature comparison](docs/WEB_FEATURE_PARITY.md)
