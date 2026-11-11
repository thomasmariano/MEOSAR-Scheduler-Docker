# Browser feature migration notes

This file records development history. References to the desktop describe the source of migrated behavior; this web repository builds independently.

# Desktop-to-browser feature parity

This inventory describes implemented browser functionality, not a claim of a
fully tested production deployment. The default local configuration binds to localhost. Ubuntu LAN deployment is intentionally shared and login-free; see UBUNTU_LAN_DEPLOYMENT.md.

| Feature | Browser status |
| --- | --- |
| Shared visibility, scoring and scheduling | Uses the desktop controller/core |
| Mission name/type, UTC event time | Implemented |
| Before/after hours and minutes, range preview | Matches desktop: up to 168 h 59 min before and after |
| Location, satellite and antenna libraries | Built-in defaults; searchable add/edit/delete controls |
| Mission satellite/antenna selection | Implemented; independent of persistent library defaults |
| Angular separation and weighted alternate locations | Shared engine; saved locations or coordinates |
| Local TLE files and browser folders | Multi-file import and optional combined source |
| Server TLE folder | Configured read-only Docker mount |
| Current CelesTrak and Space-Track records | Existing desktop provider adapters |
| Automatic nearest-epoch TLE selection | Same desktop per-satellite selection routine across imported library |
| Epoch ages/missing records/selection | Select all, deselect old, apply mission selection |
| Three shareable graphs | Generated in isolated worker jobs |
| Interactive assignment review | Timeline, inspector and assignment table |
| Validated schedule edits | Multi-change local draft, draft undo/redo, Apply/Discard, draft-aware coverage, unsaved-close warning and separate saved revisions |
| Machine-readable schedule text and companion metadata | Original and edited exports; diagnostics stay separate |
| Schedule/TLE diagnostics | Original/imported job notices; current edited assigned-contact totals and handoffs recalculated separately |
| Saved mission inputs | Server presets, archive, restore a completed job |
| Workspace persistence and reset | Browser-local mission fields, theme, output mode and collapsible sections |
| Result freshness | Form-field comparison; library changes explicitly require regeneration |
| Existing schedule loading | Desktop text/CSV parser and exported JSON; optional metadata; explicit antenna mapping into a separate job |
| Embedded simulator preview | On-demand expandable iframe; released when collapsed |
| Simulator | Existing desktop globe/dashboard through an HTTP adapter; completed schedule picker and Load Latest |
| Simulator TLE refresh/replay | Import/download source shortcut; separate replay job preserves assignments and frozen resources |
| Playback/seek/speed and assignment navigation | Shared simulator browser controls |
| Orbit/ground tracks, layers, state colors and inspector | Shared renderer; cached server orbit calculations |
| Pinned coverage locations | Shared server monitoring library with create/edit/delete; active pins remain per-browser/job |
| Scheduler/simulator comparison | Shared elevation routine and each job's frozen TLE input |
| Coverage-event navigation | Shared sampled search; bounded 20-second server search |
| Custom top/right dashboard widgets | Shared desktop widget controls; per-browser/job persistence |
| Video studio/export | Still/live preview, current/clean layers, 12/24/30 FPS plus 10/15 FPS, fixed-layout frames, MP4/WebM, cancellation/downloads; configurable limits below |
| Historical website requests | Not exposed in browser; historical files can be imported |
| Long desktop tracking windows | Desktop duration limits implemented; background job execution remains limited to 30 minutes |
| Dragging/resizing passes directly on a timeline | Not implemented; use validated editor controls |
| Users and permissions | Intentionally login-free/shared on the Ubuntu internal network, per requested deployment model |
| Retention quotas, deployment CI and rollback/backup automation | Remaining deployment work |

## Verification limits

Temporary-data tests cover core API workflows, shared validation and actual
headless scheduling/orbit calculations. Desktop providers were tested with
simulated responses rather than a user's account. New browser layouts and
interactions still need visual review. A Docker rebuild on the target machine
is required after source changes. Both Linux CPU architectures and the final
network environment still need deployment validation.


## Video export transport

The browser tab renders the shared desktop compositor while FFmpeg in Docker
encodes the PNG stream. Keep the tab open; this is not an unattended server
render worker. Still preview covers one timestamp; full export preflight scans
every output timestamp to lock margins and prevent moving panels. Defaults are
one active encoder, 18,000 frames, 600 seconds of output and two hours of encoder
session time. Duration/frame/session limits are configurable in Compose. PNG frames are size/dimension/sequence checked. Stored completed
videos persist in the data volume; automatic completed-video retention is not
yet implemented. Actual browser composition and the updated container need
visual/end-to-end review despite successful backend encoding tests.

## 2.0.3 workspace refinement

- Named saved schedule snapshots preserve result files, TLEs and resource configuration. Saved edited revisions remain available to the simulator even after leaving the editor undo history.
- Missions & calendar separates saved mission inputs, saved schedule snapshots and paginated previous jobs. Calendar dates/times are UTC; saving inputs adds planned events.
- Direct satellite/antenna editors and an explicit TLE epoch/information entry point reuse existing server library tools.
- Assignment selection opens the draft editor with the selected pass and a side editing form. Full schedule validation still gates Apply.
- UTC inputs use explicit 24-hour ISO text. Light-theme contrast, new-window graph links and dialog X controls are shared browser presentation changes.
- Simulator launch controls support opening after a completed generation. Embedded preview hides surrounding dashboards.
- Video Studio includes a manual camera-angle picker; simulator location labels seek free nearby space and use leader lines.

This is an implementation update, not a claim of complete desktop parity. Verify appearance, camera controls and representative real missions in the browser before deployment. The desktop application remains a separate interface using shared calculations.

### Shared operations and timeline follow-up

Operations & notices stores a shared server board. An explicit antenna down/repair action updates the persistent antenna library with a revision guard. Resolving a notice does not change availability. Browsers poll shared libraries/notices every 15 seconds; completed jobs retain frozen inputs. Mission presets and the calendar are already shared server data, rather than public cloud storage.

The interactive assignment view now follows saved edit revisions, including undo/redo. TLE source and mean signed epoch age appear above the workspace for the selected calculation; automatic selections record available source filenames for new jobs. Original job diagnostics are accessed through the epoch window. Preview playback includes a scrubber, camera positioning is grouped with the camera selector, and date/time inputs display a space separator in 24-hour UTC.

### Workspace reset, announcements and presentation

Reset current mission confirms whether the selected schedule revision has a saved snapshot and whether current inputs match a saved preset. It clears the browser workspace without deleting history, saved missions or shared notices; background jobs continue. An open schedule draft must be applied/discarded and closed first.

The header notification badge tracks unread active notices per browser using local storage. Shared announcements support notes and an Update category for developer messages. Saving a mission preset (calendar event) creates an Event announcement. No per-user roles or internet cloud service is introduced.

The TLE banner includes a configurable old-epoch count (default 10 days) and a direct View epochs button. Antenna selection starts expanded. Graph images themselves open full-size, original download files live in a collapsed section at the bottom, and dialogs retain an X at the top with their Close action at the bottom. Camera angle fields and action buttons have a dedicated spaced layout.

### Epoch sorting and notification cleanup

The epoch table supports ascending/descending sorting on Use, MEOSAR, NORAD, epoch, numeric age and status; missing epochs remain last. All original generated image sections start collapsed regardless of old saved layout preferences. The notification header control uses a compact SVG bell. The operations board opens with announcements visible and the composer collapsed; posting uses a single full-width notes field. Existing historical messages remain readable alongside their notes.

Add future event is available beside Missions & calendar and within that window. It collects a future UTC time, launch/landing type and locations, then saves shared mission inputs and creates the existing Event announcement. It does not generate or queue a schedule.

### Header and output action layout

Header actions are Calendar, Open simulator, Announcements and the notification bell. Calendar contains Add future event, with a native date picker and separate 24-hour UTC time. Load existing mission remains in the input toolbar. Save schedule appears beside completed outputs; Reset appears for a selected/configured mission. Duplicate simulator launch buttons were removed.

The bell opens notifications with the composer hidden and visible Read/Unread labels; unread entries are highlighted. Announcements opens the posting composer expanded. Read status remains browser-local and is updated when individual/all notices are marked read.

### Cleanup and responsive layout

Clear previous jobs removes terminal jobs from shared history without deleting their files or breaking saved schedule references; running jobs remain. Notifications can be deleted individually or cleared globally with confirmation, without restoring antenna availability. Calendar events can be deleted from their event window or saved-input entry; deletion archives the preset and resolves its linked announcement, preserving historical calculations.

Save and Reset are inside Schedule jobs. Header actions wrap as width changes, the main layout stacks on smaller screens, and dialogs/forms fit narrower viewports. Dense timelines and tables retain horizontal scrolling for legibility. Status banners have light-mode colors and a dismiss X. The simulator preview has an Open active schedule control and follows the currently saved revision.

### Duration alignment and history grouping

Hours/minutes use a dedicated two-column input grid that does not inherit the narrow-screen single-column rule. Previous jobs starts collapsed, and contains both reuse-selected-inputs and clear-selected/clear-all controls. Clearing a selected running or queued job is rejected. The quality metric explicitly describes minutes with fewer than three distinct assigned satellites; it is not the 3-degree elevation mask.

### Coverage and input clarity

Full coverage reports the percentage and minutes with at least three distinct tracked satellites, recomputed from the displayed saved schedule. It is a count-based display threshold, not a link-budget or localization guarantee. Original downloads hide without a completed schedule. Mission and assignment dates have native date pickers; UTC time remains explicit. TLE selection/import controls are collapsed, retaining CelesTrak, Space-Track, local upload and mounted-folder sources. Simulator auto-open is removed from the UI.

Alternate locations explain the existing 0.1–10 relative priority scale. The assignment editor uses Confirm change / Save validated changes, collapses advanced revision controls, validates date order locally and correctly parses the space-separated UTC display. Shared announcements remain in-app notices polled every 15 seconds; they are not email or operating-system push notifications.
