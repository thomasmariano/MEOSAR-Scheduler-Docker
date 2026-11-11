"""Load editable local web assets and inline them for the existing Qt bridge.

Classic JavaScript shares state across these files. Keep SCRIPT_ORDER intact.
Inlining retains offline texture replacement and the existing setHtml base URL.
"""
from pathlib import Path

SCRIPT_ORDER = ('state_and_controls.js', 'dashboard_widgets.js', 'video_compositor.js', 'orbit_bridge.js', 'globe_renderer.js')
WEB_DIRECTORY = Path(__file__).resolve().parent / "web"


def load_dashboard_html():
    try:
        template = (WEB_DIRECTORY / "dashboard.html").read_text(encoding="utf-8")
        css = (WEB_DIRECTORY / "dashboard.css").read_text(encoding="utf-8")
        javascript = "\n".join((WEB_DIRECTORY / name).read_text(encoding="utf-8") for name in SCRIPT_ORDER)
    except OSError as exc:
        raise RuntimeError(f"Simulator web resources are missing or unreadable in {WEB_DIRECTORY}. Install the entire simulation/web folder; packaged builds must include it.") from exc
    return template.replace("__MEOSAR_DASHBOARD_CSS__", css).replace("__MEOSAR_DASHBOARD_JS__", javascript)
