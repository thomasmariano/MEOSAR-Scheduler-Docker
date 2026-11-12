# Regular folders for MEOSAR files

An optional host-folder mode keeps files accessible outside Docker. Configure
`compose.files.yaml` alongside the base configuration and HTTPS (if enabled).
Named-volume storage remains the default when host-folder mode is not selected.

```text
MEOSAR Files/
  Application Data/       internal saved missions, libraries, jobs and canonical outputs
  Exports/
    Schedules/           original schedules and validated saved revisions
    Graphs/              generated schedule/coverage images
    Videos/              completed videos
    Saved missions/      named saved schedule exports
  TLE Library/           readable copies of imported/downloaded TLEs and metadata
  TLE Imports/           drop files here, then import through the app
```

Each export directory includes a mission/source name and unique ID. Outputs from
different jobs do not overwrite each other. Readable copies refresh within about
15 seconds. The internal jobs, edited schedules and saved snapshots remain the
source of truth. Files are copied atomically so reports/videos are not exposed
half-written. Large initial video copies can take longer. Readable copies consume additional
disk space, particularly for videos; include them in capacity planning.

## Reading and importing files

Open the host folder in Finder or File Explorer. Exported schedules retain their
machine-readable text format; the metadata is a separate file. Edited exports
appear separately from Original. Video files appear only after successful encoding.

For new TLEs, place .tle/.txt/.3le files in TLE Imports, then choose
**TLE source & imports → TLE sources & folders → Server folder**, select the files,
and import. Dropping a file does not automatically activate it. TLE Library is
an output copy, not the input folder.

This is one-way publishing. Editing an exported copy does not edit the app's
schedule. Deleting an export copy can cause it to be recreated on the next scan.
Do not edit/delete files under Application Data manually while the app is running.
Clearing job history still does not physically delete the source job records.

## Local Mac installation

The configured local folder is `~/Documents/MEOSAR Files`. Local ignored .env
selects compose.files.yaml, the absolute folder path and the current account's
numeric UID/GID. Existing data was copied from the Docker volume and checked;
the old volume was retained. The browser address remains the configured HTTPS
address. This folder is local to the Mac; Git does not transfer its data to Ubuntu.

The container runs with that account's non-root UID/GID so newly written files
can be opened by the host user. Container application code remains read-only
owned image resources; mutable data goes into the mounted folders. Never set
MEOSAR_UID=0 to work around permission problems.

## Fresh Ubuntu setup

Choose a folder owned by the non-root deployment account, for example
`/home/deploy/MEOSAR Files`. Create all five top-level directories shown above.
Use `id -u` and `id -g` to get that account's actual IDs. In ignored ubuntu.env:

```dotenv
MEOSAR_FILES_DIRECTORY=/home/deploy/MEOSAR Files
MEOSAR_UID=1000
MEOSAR_GID=1000
```

Those are examples: replace the account/path/IDs. Use an absolute path; do not put
literal $HOME or ~ into the env-file value. Preserve MEOSAR_HTTPS=1 and the correct
certificate/bind settings. The server helper automatically includes the files
overlay when MEOSAR_FILES_DIRECTORY is set:

```bash
bash scripts/server.sh start
```

On a fresh installation, the empty Application Data directory is seeded normally.
For an existing installation, first take a consistent backup and stop the writer.
Restore the trusted backup into an EMPTY Application Data directory as its owning
account, verify ownership, then enable the overlay. Do not switch an existing
installation to an empty folder and assume its old Docker volume was lost.
Retain the original volume until the migration is verified; never delete it as
part of selecting a different storage mount.

For manual Compose commands, include `-f compose.files.yaml` too. The local .env
can set COMPOSE_FILE=compose.yaml:compose.https.yaml:compose.files.yaml. Keeping the
same overlay/env settings on updates avoids accidentally selecting another store.

## Access from other computers

A browser download copies a file onto the client computer. The mounted folder
is on the SERVER and does not appear automatically on every user's computer.
The network engineer can provide a restricted SMB/NFS share for Exports and
TLE Imports if direct network-folder access is wanted. Do not share Application
Data or certificate/private-key directories broadly. File sharing permissions
are separate from the application's shared LAN access.

## Backups and Git

The server helper still backs up /data, which includes canonical schedules,
TLEs and videos. Exports/TLE Library are regenerable copies. Back up TLE Imports
separately if its original files matter. A filesystem backup of Application Data
must be made with application writers stopped for consistency.

Do not commit this folder or its mission/TLE data to GitHub. Keep it outside the
source checkout. Local .env/ubuntu.env contain the host-specific folder settings
and remain ignored. The files overlay and publishing code can be committed and
reused on Ubuntu without carrying any Mac data or absolute Mac paths.

## Browser Files library and Export schedule

Use **Files** in the header to browse published schedules, graphs, videos and
TLEs. Search by filename/mission/folder and choose a category. Download copies
that file to the current computer, usually its browser Downloads folder. Browsers
may ask where to save according to the user's preferences; the web app cannot
force an arbitrary local folder or open a server folder in Finder.

**Export schedule** appears beside a completed schedule. Choose the original or
current saved revision. TXT downloads keep the desktop five-column format
(NORAD, MEOLUT, antenna, UTC start, UTC end), without notes or diagnostic text.
The filename follows the desktop preset:

`YYYYMMDD HHMM - YYYYMMDD HHMM Mission Location coverage.txt`

Dates use the first/last actual assignment, in UTC. Saved edit names add a short
revision ID to distinguish them. The metadata companion has the exact same stem
with `.metadata.json`. The optional ZIP contains the TXT and metadata together,
and can include the job's frozen TLE records. Extract before loading the desktop
simulator; keep TXT/metadata beside one another. In the simulator, Upload schedule accepts the ZIP directly and reads its
metadata/TLE without returning to the scheduler. For a standalone TXT, choose
the metadata companion and TLE source if needed, and review antenna mappings. Matching TLEs and satellite/antenna configuration still matter
for replay; a filename alone does not define orbital state.

**Save schedule** stores a named server snapshot; **Export schedule** downloads
files onto this computer. Readable server copies continue appearing automatically
under MEOSAR Files. Browser browsing exposes only published Exports/TLE Library,
not Application Data or certificates. Symlink paths outside those roots are
excluded. Up to 10,000 directory entries are scanned; use folder/search filters
in the UI and a retention policy if the library grows.

Old generated generic schedule filenames are replaced by descriptive copies only
when their bytes still match the canonical source. Manually modified old copies
are preserved. Canonical application filenames and saved schedule contents are
not renamed or rewritten by the readable-export feature.

## Upload directly into the simulator

Use Upload schedule on the simulator toolbar, or Load schedule / latest → Upload
schedule and simulate. TXT/CSV/JSON and exported ZIP bundles are supported. ZIPs
are bounded and read in memory; no archive paths are extracted onto the server.
Review the detected assignments, locations, TLE source and antenna mappings, then
choose Load into simulator. The imported assignments are retained in a separate
analysis job. The same tab opens the simulator when analysis finishes. Closing
the dialog does not cancel an already queued job.

If no completed jobs exist, the main Open simulator action opens the upload page
instead. Missing satellite library entries or ambiguous antenna mappings still
require correction. Metadata coordinates that differ from server library records
are reported for review; replay uses the selected configured locations.
