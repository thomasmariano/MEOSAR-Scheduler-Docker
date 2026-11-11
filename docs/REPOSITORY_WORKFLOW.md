# Separate desktop and web repositories

- Desktop: https://github.com/thomasmariano/MEOSAR-Scheduler
- Web/Docker: https://github.com/thomasmariano/MEOSAR-Scheduler-Docker

This repository includes its own copies of the calculation modules, simulator
browser assets, libraries and Docker build files. No checkout or installation of
the desktop repository is required for builds or deployment.

Make web changes in this checkout, test, commit and push here. Pull this repository
on Ubuntu and run `bash scripts/server.sh update`. The server data volume remains
independent of Git. Keep host-specific ubuntu.env and live data out of commits.

Calculation fixes affecting both products must be deliberately ported and tested
in both repositories. They are no longer automatically synchronized. Avoid copying
Qt interface modules into the server image. requirements-web.lock.txt controls
container dependencies; requirements-web.txt lists direct requirements.

The Compose project is meosar-web, separate from the original development stack.
Existing Docker data is not automatically moved into this project's volume.
For local testing alongside the old stack, copy .env.example to .env and open
http://localhost:8081. On Ubuntu use ubuntu.env and the server helper.

The local source snapshot used for initial separation included uncommitted web
migration work, so the desktop repository's last commit alone does not identify
all files in this initial web import. Future web commits are independently tracked.
