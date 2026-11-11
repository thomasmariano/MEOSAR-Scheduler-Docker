# MEOSAR Scheduler Docker

**Developed and maintained by Thomas Mariano.**

A browser-based application for MEOSAR satellite visibility analysis, mission
planning, antenna scheduling, and satellite simulation. This is the Docker/web
version of my [MEOSAR Scheduler desktop application](https://github.com/thomasmariano/MEOSAR-Scheduler).

I built the desktop scheduler first, then added a simulator and video export.
I am now moving those tools into a shared browser application so users on an
internal network can access them without installing the desktop application.
The desktop and browser interfaces use shared Python calculation modules.

**Current development version:** 2.0.3  
**Deployment target:** an internal Ubuntu server running Docker Compose

> This repository currently contains the project README. The runnable web
> application and deployment files have not yet been uploaded here. The commands
> below apply to the original source repository once its web migration files are
> committed and published.

## Features

- Mutual satellite visibility calculations between a ground station and mission site.
- Mission tracking windows with UTC event times and before/after coverage.
- Antenna-compatible satellite assignments and coverage preferences.
- Interactive schedule review, validated editing, and schedule/image exports.
- Satellite, antenna, location, and TLE libraries.
- TLE retrieval from CelesTrak and Space-Track, browser uploads, and server folders.
- Saved missions, previous jobs, and a shared launch/landing calendar.
- Shared announcements and antenna down/repair updates for future calculations.
- Interactive globe, satellite tracks, pinned locations, and coverage displays.
- Video export with camera positioning and selectable information panels.
- Light and dark themes.

## How it works

```text
Users on the internal network
          |
          v
Browser interface
          |
          v
Ubuntu server / Docker Compose
  FastAPI + shared Python scheduling calculations
  Satellite propagation + FFmpeg video encoding
          |
          v
Persistent application data volume
```

The browser sends mission inputs to the server. The server performs scheduling
calculations and stores results for users to reopen. The simulator renders in
the browser using server-provided satellite data. Video export uses frames from
the browser and encodes them with FFmpeg on the server, so the exporting browser
tab must stay open until the export finishes.

The server image does not require PyQt6. Native Linux amd64 and arm64 builds are
supported by the Dockerfile; target-server testing is still needed.

## Technology

| Component | Technology |
| --- | --- |
| Calculations | Python, Skyfield, SGP4 |
| Web service | FastAPI, Uvicorn |
| Browser interface | HTML, CSS, JavaScript |
| Graphs | Matplotlib |
| Video encoding | FFmpeg |
| Deployment | Docker, Docker Compose, Ubuntu |
| Desktop version | Python, PyQt6 |

## Running the application

The application source is currently maintained in
[MEOSAR-Scheduler](https://github.com/thomasmariano/MEOSAR-Scheduler). Ensure the
selected source commit includes the web migration and server helper before
attempting deployment.

Install Docker Engine and the Compose plugin using the
[official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
Then, in the application checkout:

```bash
cp ubuntu.env.example ubuntu.env
nano ubuntu.env
bash scripts/server.sh start
bash scripts/server.sh status
```

Set the bind address and port in `ubuntu.env` for the intended network. The
current application port is **8080**. The local development default binds to
**127.0.0.1**; the Ubuntu configuration can bind to a server LAN address.

Once deployed, users open the server address in their browser. They do not need
a local Python environment or FFmpeg installation.

## Network deployment

My intended setup is a shared internal-network service without an application
login. Everyone who can reach it can access shared missions, edit libraries,
change antenna availability, and manage announcements. Network access must
therefore be restricted to the intended users/devices.

The main items to agree with the network engineer are:

- Ubuntu version, processor architecture, CPU, memory, and storage capacity.
- Internal DNS name, permitted network segments, and firewall rules.
- HTTPS certificate and reverse proxy configuration.
- Outbound access for GitHub, Docker/package downloads, and online TLE sources.
- Backup location, retention, monitoring, and maintenance responsibility.

The current service uses HTTP by default. Configure HTTPS before entering real
Space-Track credentials or using sensitive mission data. Docker-published ports
can bypass ordinary UFW filtering; review
[Docker's firewall guidance](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

## Saved data

Application data is stored in the Docker volume mounted at `/data`. This includes
libraries, TLEs, missions, schedules, edits, calendar events, announcements, and
videos. The optional server TLE-import folder is mounted read-only and is backed
up separately if its original files need to be retained.

Git updates application code; it does not synchronize my Mac's saved browser
data with the server. Container updates preserve the server data volume.
Existing server library edits are not overwritten by updated bundled defaults.

**Do not run `docker compose down -v` on the live deployment:** it deletes the
persistent volume. Clearing previous jobs removes them from history but does
not reclaim their stored files.

## Updates and backups

My update workflow is to test changes locally, commit and push them, then deploy
a tested commit on the server. For a server following the source repository's
`main` branch:

```bash
git pull --ff-only origin main
bash scripts/server.sh update
```

Wait for active calculations and video exports to finish first. The helper
creates a backup, rebuilds the image, restarts the service, and checks its health.
Updates involve short downtime. Use tested tags/commits for controlled releases;
there is no automatic deployment webhook currently configured.

```bash
bash scripts/server.sh backup
bash scripts/server.sh logs
```

Keep backup copies off the server and test a restore into a separate instance.
Code rollback and data restoration are deliberate operations, not automatic.

## Current limitations

- Ubuntu deployment and performance testing are still pending.
- No application accounts, permission roles, or person-level audit trail.
- CPU/memory quotas, total storage limits, and retention need deployment configuration.
- Dependency and container vulnerability scanning and penetration testing are pending.
- Shared announcements are in-app notices, not email or desktop push notifications.
- Notification read status and some display preferences are local to each browser.

The container already runs as a non-root user, drops Linux capabilities, and
uses bounded uploads/jobs. These protections do not replace a security review.
This is a mission-planning and visualization tool; operational acceptance of
its calculations is separate from approving the network deployment.

## Development

I maintain the project and its scheduling/simulation features. The next step is
to test the browser version on the intended Ubuntu server, verify persistence
and backups, and agree the network configuration before wider use.
