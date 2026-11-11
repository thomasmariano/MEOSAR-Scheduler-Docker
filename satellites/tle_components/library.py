"""Library responsibilities extracted from the public TLE manager."""
from datetime import datetime, timezone
from pathlib import Path
import shutil


class TLELibraryMixin:
    def create_directories(self):

        self.USER_TLE_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True
        )

        self.migrate_old_tle_files()


    @staticmethod
    def get_file_datetime(
        file_path
    ):

        file_path = Path(
            file_path
        )

        filename = file_path.stem

        timestamp = filename

        for prefix in (
            "gnss_",
            "tle_",
            "manual_",
            "celestrak_",
            "spacetrack_",
            "space_track_",
        ):

            if timestamp.startswith(
                prefix
            ):

                timestamp = (
                    timestamp[
                        len(prefix):
                    ]
                )

                break

        try:

            return datetime.strptime(
                timestamp,
                "%Y-%m-%d_%H-%M-%S"
            ).replace(
                tzinfo=timezone.utc
            )

        except ValueError:

            pass

        try:

            return datetime.fromtimestamp(
                file_path.stat().st_mtime,
                tz=timezone.utc
            )

        except OSError:

            return None


    @staticmethod
    def get_file_age_hours(
        file_path
    ):

        from satellites.tle_manager import TLEManager
        file_datetime = (
            TLEManager.get_file_datetime(
                file_path
            )
        )

        if file_datetime is None:

            return None

        now = datetime.now(
            timezone.utc
        )

        return (
            now - file_datetime
        ).total_seconds() / 3600


    def get_user_tle_files(self):
        self.USER_TLE_DIRECTORY.mkdir(parents=True,exist_ok=True)
        self.migrate_old_tle_files()
        return sorted(
            (path for path in self.USER_TLE_DIRECTORY.rglob("*")
             if path.is_file() and path.suffix.lower() in {".tle",".txt",".3le"}
             and "Run Selections" not in path.relative_to(self.USER_TLE_DIRECTORY).parts),
            key=lambda path: str(path)
        )


    def migrate_old_tle_files(
        self
    ):

        old_directories = [

            self.USER_TLE_DIRECTORY
            / "Downloaded"
            / "CelesTrak",

            self.USER_TLE_DIRECTORY
            / "Downloaded"
            / "Space-Track",

            self.USER_TLE_DIRECTORY
            / "Manual",

        ]

        for directory in old_directories:

            if not directory.exists():

                continue

            for source_file in (
                list(directory.glob("*.tle"))
                +
                list(directory.glob("*.txt"))
            ):

                destination = (
                    self.USER_TLE_DIRECTORY
                    / source_file.name
                )

                if destination.exists():

                    stem = source_file.stem
                    suffix = source_file.suffix
                    counter = 1

                    while destination.exists():

                        destination = (
                            self.USER_TLE_DIRECTORY
                            /
                            f"{stem}_{counter}{suffix}"
                        )

                        counter += 1

                try:

                    shutil.move(
                        str(source_file),
                        str(destination)
                    )

                except OSError:

                    continue


    def import_manual_tle(
        self,
        file_path
    ):

        source_path = Path(
            file_path
        )

        self.validate_tle_file(
            source_path
        )

        try:

            source_path.relative_to(
                self.USER_TLE_DIRECTORY
            )

            return source_path

        except ValueError:

            pass

        timestamp = (
            datetime.now(
                timezone.utc
            ).strftime(
                "%Y-%m-%d_%H-%M-%S_%f"
            )
        )

        destination = (
            self.USER_TLE_DIRECTORY
            /
            f"manual_{timestamp}.tle"
        )

        shutil.copy2(
            source_path,
            destination
        )

        return destination


    def save_downloaded_tle(
        self,
        tle_data,
        source
    ):

        self.USER_TLE_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True
        )

        timestamp = (
            datetime.now(
                timezone.utc
            ).strftime(
                "%Y-%m-%d_%H-%M-%S"
            )
        )

        source_name = (
            source.lower()
            .replace("-", "_")
        )

        file_path = (
            self.USER_TLE_DIRECTORY
            /
            f"{source_name}_{timestamp}.tle"
        )

        file_path.write_text(
            tle_data,
            encoding="utf-8"
        )

        self.validate_tle_file(
            file_path
        )

        return file_path

