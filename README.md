# MEOSAR Scheduler Docker

A self-hosted Docker web application for MEOSAR mission planning, satellite
visibility analysis, antenna scheduling, and globe simulation. Access a shared
workspace from a browser, with HTTPS, persistent storage, schedule editing,
TLE management, and video export.

**Developed and maintained by Thomas Mariano.**
**Version: 2.0.3**

```text
Browser (HTTPS :4443)
          |
          v
nginx (certificate + private key)
          |
          v
FastAPI backend :8080 (internal only)
  | Scheduling, propagation, graphs, FFmpeg encoding
  v
Persistent application storage
```

This is a standalone repository. No desktop application, local Python environment,
or separate FFmpeg installation is required on client computers.

## Features

- **Mission planning** — UTC event day/time and tracking windows before and after an event.
- **Satellite scheduling** — mutual visibility, antenna band compatibility,
  angular separation, and ordered alternate-location priorities.
- **Interactive editing** — assignment timeline, coverage-based pass additions,
  validated changes, draft history, and saved revisions.
- **Coverage analysis** — tracking graphs, full-coverage intervals, removed-pass
  details, missing-TLE information, and epoch review.
- **Resource libraries** — saved locations, satellites, and antennas with
  individual add, edit, and delete controls.
- **TLE management** — CelesTrak, Space-Track, local files/folders, server folders,
  and automatic epoch selection. Space-Track requires an account.
- **Saved work** — missions, previous jobs, shared calendar, and announcements.
- **Antenna availability** — shared down/repair notices for future calculations.
- **Globe simulator** — satellite positions, orbit/ground tracks, location coverage,
  monitoring pins, playback, and customizable dashboards.
- **Video export** — camera controls, selectable information panels, and server encoding.
- **Downloads** — machine-readable schedules, simulator ZIP packages, graphs, and videos.
- **Appearance** — light/dark themes and grouped simulator controls.

## Requirements

- Docker Engine and Docker Compose **2.24.4 or newer**.
- Linux server with an **amd64 or arm64** processor; the image builds for the host architecture.
- Git for source-based installation and updates.
- A certificate matching the hostname/IP used to access the application.
- Network access to image/package repositories during builds.
- Access to CelesTrak/Space-Track for online TLE retrieval, or local TLE files.

For Ubuntu, follow the [official Docker installation instructions](https://docs.docker.com/engine/install/ubuntu/).

## Quick start

### 1. Clone and configure

```bash
git clone https://github.com/thomasmariano/MEOSAR-Scheduler-Docker.git
cd MEOSAR-Scheduler-Docker
cp ubuntu.env.example ubuntu.env
nano ubuntu.env
```

Set the server bind address and HTTPS port:

```dotenv
# Replace the example address with the server's LAN IP.
MEOSAR_BIND_ADDRESS=192.168.1.50
MEOSAR_HTTPS=1
MEOSAR_HTTPS_PORT=4443
```

Use `0.0.0.0` to listen on all interfaces, or a specific server address to limit
the binding. Keep helper-script env settings unquoted as shown in the template.
`ubuntu.env` is local configuration and is ignored by Git.

### 2. Add the certificate

```text
MEOSAR-Scheduler-Docker/
└── certs/
    ├── server.crt
    └── server.key
```

Use a certificate issued by an internal CA, or a self-signed certificate with
client trust configured. The certificate must include the actual server
hostname/IP in its Subject Alternative Names. A localhost certificate does not
identify a remote server. Never commit the private key.

To generate a self-signed certificate on the server, replace these examples:

```bash
bash scripts/create-cert.sh meosar.internal.example 192.168.1.50
```

The script refuses to overwrite existing certificate files. It creates a
certificate valid for 365 days; it does not configure browser trust.
See [HTTPS setup](docs/HTTPS.md) for certificate installation and renewal.

### 3. Build and run

```bash
bash scripts/server.sh start
bash scripts/server.sh status
```

The helper selects HTTPS, builds the image, starts the containers, and waits
for health checks. The first build downloads dependencies and FFmpeg.

Open:

```text
https://YOUR-SERVER-NAME:4443
```

Use the name/IP covered by the certificate. Deploy at the URL root;
subpath hosting such as `/meosar/` requires additional configuration.

### 4. Configure a mission

- Open **Manage libraries** to review saved locations, satellites, and antennas.
- Add/edit/delete individual entries as needed. Whole-library JSON uploads are disabled.
- Open **TLE source & imports → TLE sources & folders** to download or import TLEs.
- Enter a mission name, UTC event day/time, tracking window, ground station, and mission site.
- Review satellite and antenna selections, then generate the schedule.

A fresh installation includes default resource libraries. TLEs, jobs, saved
missions, calendar entries, and announcements start empty. Existing runtime
data from another installation is not required.

### 5. Review, save, and simulate

- Select an assignment in the interactive timeline to inspect or edit it.
- Use **Save schedule** to preserve a named mission snapshot on the server.
- Use **Export schedule** to download a copy to the current computer.
- Choose the recommended ZIP package to keep the schedule, metadata, and TLEs together.
- Open the simulator for playback or upload an existing schedule directly.
- Keep the browser tab open until a video export finishes; the browser renders
  frames and the server encodes them with FFmpeg.

## Ports used

| Port | Purpose |
| --- | --- |
| **4443** | HTTPS dashboard, published on the configured server address |
| **8080** | FastAPI backend, internal only when HTTPS is enabled |

The supplied HTTPS configuration does not publish ports 80 or 443 and does not
provide an HTTP redirect. `MEOSAR_PORT` is used only in HTTP mode.

## Storage and downloads

By default, a Docker named volume stores application data at `/data`. Container
updates preserve saved missions, libraries, schedules, TLEs, notices, and videos.
Updated bundled defaults do not replace existing server library edits.

For regular server folders, configure `MEOSAR_FILES_DIRECTORY`, `MEOSAR_UID`,
and `MEOSAR_GID` before first startup. Create the directories and set ownership
as described in [file storage](docs/FILE_STORAGE.md). The helper automatically
includes `compose.files.yaml` when this option is configured.

```text
MEOSAR Files/
├── Application Data/   # Canonical application data; do not edit manually
├── Exports/            # Schedules, graphs, videos, saved mission exports
├── TLE Library/        # Readable copies of TLE sources
└── TLE Imports/        # Files available for browser import
```

Browser downloads go to the client computer, normally its Downloads folder.
The server folder does not automatically appear on other computers; direct
folder access requires a separate network share. Keep Application Data and
certificate/private-key directories restricted.

## Updates

Test and push changes to this repository from the development computer. Then,
on the server, wait for active calculations and video exports to finish:

```bash
cd /path/to/MEOSAR-Scheduler-Docker
git pull --ff-only origin main
bash scripts/server.sh update
```

Replace the path with the installation directory. The helper requires a clean
Git checkout, backs up `/data`, rebuilds/restarts the application, and checks
container health. Updates involve brief downtime. Users should hard-refresh
their browsers afterward.

GitHub pushes do not automatically deploy. Keep the same Compose project name
(`meosar-web`), env file, and storage settings across updates. Local env files,
certificates, and runtime data are not transferred through Git.

## Useful commands

```bash
# Container status
bash scripts/server.sh status

# Recent logs
bash scripts/server.sh logs

# Back up application data
bash scripts/server.sh backup

# Build/start the configured installation
bash scripts/server.sh start

# Back up and deploy updated source
bash scripts/server.sh update

# Show the deployed commit
cat .deployment/deployed-commit
```

Backups are timestamped under ignored `backups/`. Keep copies off the server
and test restoration. The `/data` backup includes canonical schedules, libraries,
TLEs, saved missions, calendar, announcements, and completed videos. Back up
certificates, the env file, and original TLE-import files separately as needed.
Browser preferences and notification read status are stored in each browser.

**Do not use `docker compose down -v` for routine maintenance:** it removes
persistent named volumes. Clearing job history does not delete stored job files;
plan storage capacity and retention, especially for videos. Rollback and restore
are manual operations; see the [deployment guide](docs/UBUNTU_LAN_DEPLOYMENT.md).

## Network and validation notes

- Shared internal-network access is used without application logins or roles.
  Anyone with access can modify shared data; limit network access accordingly.
- HTTPS provides transport encryption, not application permissions.
- Check [Docker-aware firewall rules](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
  when publishing the service.
- Builds require access to GitHub, Docker registries, Debian repositories, and PyPI.
- Announcements are in-app notices, not email or desktop push notifications.
- Validate schedules, simulation, video export, persistence, and backup recovery
  on the target server before operational use. Local testing does not establish
  target-server performance or operational acceptance of the calculations.
- Plan certificate renewal, storage retention, resource limits, and security maintenance.

## Project structure

```text
MEOSAR-Scheduler-Docker/
├── web/                    # Browser interface and FastAPI routes
├── core/                   # Scheduling, scoring, visibility, diagnostics
├── scheduler/              # Calculation workflow
├── satellites/             # TLE management and source adapters
├── simulation/             # Orbit engine and shared browser simulator assets
├── graphs/                 # Coverage and schedule plots
├── reports/                # Visibility reporting
├── config/                 # Default resource libraries and configuration helpers
├── assets/                 # SAR logo and globe texture
├── deploy/nginx.conf        # HTTPS reverse proxy
├── certs/                  # Local certificate/key; ignored by Git
├── scripts/                # Server lifecycle and certificate helpers
├── docs/                   # Deployment, HTTPS, storage, and repository guides
├── Dockerfile
├── compose.yaml
├── compose.https.yaml
├── compose.files.yaml
└── ubuntu.env.example
```

## Documentation

- [Ubuntu installation, updates, and recovery](docs/UBUNTU_LAN_DEPLOYMENT.md)
- [HTTPS and certificates](docs/HTTPS.md)
- [File storage and downloads](docs/FILE_STORAGE.md)
- [Repository workflow](docs/REPOSITORY_WORKFLOW.md)
- [Desktop/web feature comparison](docs/WEB_FEATURE_PARITY.md)
- [Desktop application](https://github.com/thomasmariano/MEOSAR-Scheduler)
