# MEOSAR Scheduler — Network Deployment Handoff

**Prepared for:** network/server engineering review  
**Project owner/developer:** Thomas Mariano  
**Application target:** MEOSAR Scheduler web version 2.0.3  
**Prepared:** November 11, 2026  
**Status:** development build; controlled deployment testing requested

This repository explains the proposed deployment. It is a documentation handoff,
not a second application codebase and not an assertion of security approval.

Application source: [thomasmariano/MEOSAR-Scheduler](https://github.com/thomasmariano/MEOSAR-Scheduler).
The local web migration and deployment helper must be committed and pushed there
before the server can deploy them. Do not assume the public/default branch already
contains the local 2.0.3 working copy. Use an explicitly identified tested commit.

## What the application does

MEOSAR Scheduler supports planning satellite tracking for search-and-rescue
support. It calculates mutual visibility between a ground station and mission
site, assigns satellites to compatible antennas, and produces schedules and
coverage graphics. Its simulator visualizes satellite motion, tracked locations
and coverage, with browser-assisted video export.

The existing desktop application uses Python/PyQt6. The browser version uses the
shared Python calculation modules behind FastAPI/Uvicorn, with HTML, CSS and
JavaScript for the interface. The goal is a central internal-network deployment
that users open in a browser instead of installing the desktop application.

Current browser functions include:

- Mission setup, resource libraries and TLE source management.
- Schedule generation, job history, validated assignment editing and exports.
- Saved missions, shared calendar events and shared operational announcements.
- Antenna availability updates that affect future calculations.
- Interactive tracking timelines and satellite simulation.
- Video export using browser-rendered frames and server-side FFmpeg encoding.

This is a planning/visualization tool. Operational suitability and calculation
acceptance must be assessed separately from network deployment approval.

## Proposed architecture

```text
Approved LAN browsers
        |
        | HTTPS (proposed; requires network configuration)
        v
Internal DNS name + reverse proxy / TLS termination
        |
        | Restricted backend connection
        v
Ubuntu server: Docker Compose
  web container: FastAPI + Uvicorn + shared calculation modules + FFmpeg
        |
        +-- Persistent Docker volume: application data
        +-- Read-only host mount: optional TLE import folder
        +-- Outbound HTTPS: CelesTrak / Space-Track when requested
```

The checked-in Compose application publishes port **8080**. The local Mac default
binds to **127.0.0.1**; the Ubuntu env example allows a LAN IP or **0.0.0.0**.
The current application configuration supplies HTTP, not TLS. The reverse proxy,
certificate, DNS, network restrictions and trusted proxy settings remain deployment
work for engineering. If the proxy is on another host, restrict backend access to
that proxy's address. Test same-origin request checks after proxy configuration.

The Dockerfile supports native Linux **amd64** and **arm64** builds. An actual
Ubuntu deployment/load test has not yet been completed. No client Python or
FFmpeg installation is required, but clients need a modern browser. Browser
rendering still contributes to simulator/video performance; the exporting tab
must stay open until video export finishes.

## Security model and confirmed limitations

**The requested model is shared LAN access without an application login.**
Network access is therefore the principal access boundary. Everyone who can
reach the application can access shared missions/results, change libraries and
antenna availability, publish/delete announcements and edit schedules. There
are no viewer/operator/admin roles and no reliable person-level audit trail.
The custom request header and same-origin checks are not authentication.

| Area | Current state / engineering action |
| --- | --- |
| Transport | HTTP by default. Configure HTTPS before entering real Space-Track credentials or using sensitive mission data. Provider-side HTTPS does not encrypt the browser-to-app leg. |
| Exposure | Restrict to approved network segments/devices; no public internet publishing is proposed. Verify from both allowed and disallowed networks. |
| Resource exhaustion | Queue, upload and encoder limits exist, but Compose has no explicit CPU/memory quotas or total storage quota. Agree limits and monitor disk, RAM and CPU. |
| Data retention | Clearing previous jobs hides history entries; it does not reclaim their files. Define retention and disk cleanup procedures. |
| Auditing | No authenticated user identity. Access logs alone do not attribute operational changes to a named person. |
| Dependencies | Python dependencies are locked to the tested development container. A dependency/container CVE scan and penetration test have not been completed. Pinning is not a security certification. |
| Credentials | The web TLE adapter uses Space-Track credentials for the request and does not intentionally persist them to libraries, jobs or exports. Ensure proxies/logging do not record request bodies or credentials. |
| Backups | Backups contain application and mission data. Restrict access and retain a verified copy off the server. |

Existing controls include non-root container execution (UID/GID 10001), dropped
Linux capabilities, no-new-privileges, a read-only TLE import mount, bounded
requests/jobs and validation of imported data. These reduce risk; they do not
replace access restrictions, HTTPS or security review.

Docker-published ports interact with host firewall rules and can bypass ordinary
UFW filtering. Follow [Docker's firewall documentation](https://docs.docker.com/engine/network/packet-filtering-firewalls/),
not only a generic UFW allow/deny recipe. FastAPI describes the proposed
[TLS termination model](https://fastapi.tiangolo.com/deployment/https/).

## Connectivity and host requirements

| Purpose | Requirement |
| --- | --- |
| User access | Approved browsers reach the internal app endpoint; proposed HTTPS on port 443 through the proxy. |
| Backend | Current container listens on 8080; restrict access according to proxy placement. |
| Source updates | Server can retrieve the application repository from GitHub, with read-only access if private. |
| Image builds | Access to Docker Hub and Python/Ubuntu package repositories for source builds. |
| Online TLEs | Outbound HTTPS to celestrak.org and www.space-track.org. |
| Offline TLEs | Browser upload and an optional read-only server import folder remain available. |
| Maintenance | Administratively controlled SSH/Docker access, backups, monitoring and sufficient writable disk. |

Exact CPU, memory, disk capacity, storage retention and concurrency requirements
must be measured using representative missions/videos. Current defaults permit
one running scheduling job plus four waiting and one video encoder at a time.
These are application limits, not performance guarantees.

## Data ownership and persistence

Runtime data is stored in the Compose named volume mounted at `/data`, separately
from the application image and Git checkout. It includes configured libraries,
TLEs, jobs, saved schedule snapshots, edits, calendar events, announcements,
monitoring locations and videos. The optional host TLE-import folder is separate
and needs its own backup if its original files matter.

- Git updates code; they do not synchronize the Mac's browser data to Ubuntu.
- Server libraries are initialized from bundled defaults only when missing;
  updating defaults in Git does not overwrite existing server library edits.
- Completed jobs retain frozen inputs. An antenna outage affects new calculations,
  not previously completed schedules.
- Notification read/unread state and some preferences are browser-local.
- Keep the normal Compose project name and env settings stable across updates.
- Do not use `docker compose down -v` on the live deployment: it removes its volume.

No operational mission records, credentials, server addresses or live data are
included in this documentation repository. Application source and bundled defaults
should receive the organization's review before they are shared or deployed.

## First deployment outline

Install Docker Engine and Compose using the [official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
Confirm the deployment account can operate Docker. Then, after the tested web
migration commit is published in the **application source repository**:

```bash
mkdir -p ~/apps
cd ~/apps
git clone https://github.com/thomasmariano/MEOSAR-Scheduler.git
cd MEOSAR-Scheduler
# Check out the tested commit/tag agreed with Thomas before starting.
cp ubuntu.env.example ubuntu.env
nano ubuntu.env
bash scripts/server.sh start
bash scripts/server.sh status
```

Configure the bind address/port for the agreed network topology. Keep `ubuntu.env`
host-specific and out of Git. Do not assume this handoff repository can be run:
Dockerfile, Compose, scripts and application modules live in the source repository.

The helper builds, starts the container, waits for its health check and records
the deployed source commit. The full source-side instructions are in
`docs/UBUNTU_LAN_DEPLOYMENT.md` after those files are published.

## Updates and recovery

Thomas develops/tests on the Mac and commits/pushes code. On Ubuntu, an operator
waits for running calculations/video exports to finish, then explicitly deploys:

```bash
cd ~/apps/MEOSAR-Scheduler
git pull --ff-only origin main
bash scripts/server.sh update
```

For controlled release promotion, agree a tested tag/commit instead of following
arbitrary newest-main changes. No GitHub webhook or automatic live deployment is
currently configured.

The helper requires a clean checkout, backs up data consistently, rebuilds,
recreates the service, waits for health and records the successful commit.
Expect short downtime; this is not a zero-downtime architecture. Users should
hard-refresh their browser after an update.

```bash
bash scripts/server.sh backup
bash scripts/server.sh logs
cat .deployment/deployed-commit
cat .deployment/previous-commit
```

Backup archives are stored in ignored `backups/`; copy them off-host. A code
rollback is a deliberate checkout/rebuild. A data format change may require a
matching data backup; automatic rollback/restore is not implemented. Test restore
into a separate Compose project/port before relying on recovery procedures.

## Engineering review and acceptance checklist

- [ ] Approve source/data classification, repository access and intended use.
- [ ] Identify Ubuntu version/architecture, CPU/RAM/disk and responsible operator.
- [ ] Agree DNS name, HTTPS certificate and reverse-proxy/backend configuration.
- [ ] Approve the shared no-login access model and permitted network segments.
- [ ] Verify published ports/firewall rules from allowed and disallowed clients.
- [ ] Approve egress destinations or plan an offline image-transfer alternative.
- [ ] Scan dependencies/container and resolve unacceptable findings.
- [ ] Configure resource limits, disk monitoring and retention responsibilities.
- [ ] Generate a representative mission and compare identical inputs/TLEs with the Mac.
- [ ] Test saved missions, schedule editing, simulator and short video export.
- [ ] Verify a test announcement in two independent browsers within 15 seconds.
- [ ] Verify persistence after container recreation and a host restart.
- [ ] Back up and restore into a separate test instance.
- [ ] Record the accepted source commit, recovery procedure and maintenance owner.

The next step is a controlled test deployment and review with engineering—not an
assertion that the application is approved for unrestricted operational use.
