"""Public MEOSAR TLE manager. Internal responsibilities live in tle_components."""
from pathlib import Path
import sys
import os
from .tle_components.records import TLERecordsMixin
from .tle_components.library import TLELibraryMixin
from .tle_components.selection import TLESelectionMixin
from .tle_components.downloads import TLEDownloadsMixin
from .tle_components.diagnostics import TLEDiagnosticsMixin


class TLEManager(TLERecordsMixin, TLELibraryMixin, TLESelectionMixin, TLEDownloadsMixin, TLEDiagnosticsMixin):
    MAX_TLE_AGE_HOURS = 7 * 24


    @staticmethod
    def get_user_data_directory():

        if sys.platform == "win32":

            base = os.environ.get(
                "LOCALAPPDATA"
            )

            if base:

                return (
                    Path(base)
                    / "MEOSAR Scheduler"
                )


        if sys.platform == "darwin":

            return (
                Path.home()
                / "Library"
                / "Application Support"
                / "MEOSAR Scheduler"
            )


        if sys.platform.startswith("linux"):

            return (
                Path.home()
                / ".local"
                / "share"
                / "MEOSAR Scheduler"
            )


        return (
            Path.home()
            / "MEOSAR Scheduler"
        )


    USER_DATA_DIRECTORY = (
        get_user_data_directory.__func__()
    )


    USER_TLE_DIRECTORY = (
        USER_DATA_DIRECTORY
        / "TLE Library"
    )


    if os.environ.get("MEOSAR_TLE_DIR"):
        USER_TLE_DIRECTORY = Path(os.environ["MEOSAR_TLE_DIR"]).expanduser()
        if not USER_TLE_DIRECTORY.is_absolute():
            raise ValueError("MEOSAR_TLE_DIR must be an absolute directory path.")

    def __init__(
        self,
        configuration=None
    ):

        self.configuration = (
            configuration.copy()
            if configuration
            else {
                "source": "Automatic"
            }
        )

        self.current_file = None
        self.current_source = None
        self.current_mode = "Automatic"

        self.create_directories()


    def set_configuration(
        self,
        configuration
    ):

        self.configuration = (
            configuration.copy()
        )


    def get_configuration(self):

        return (
            self.configuration.copy()
        )

