"""Diagnostics responsibilities extracted from the public TLE manager."""
from pathlib import Path


class TLEDiagnosticsMixin:
    def get_missing_satellites(
        self,
        file_path,
        norad_ids
    ):

        required = {
            str(norad).strip()
            for norad in norad_ids
        }

        if not required:

            return []

        try:

            analysis = (
                self.analyze_tle_file(
                    file_path
                )
            )

            available = set(
                analysis["norad_ids"]
            )

        except Exception:

            return sorted(
                required
            )

        return sorted(
            required - available
        )


    def get_available_satellites(
        self,
        file_path,
        norad_ids
    ):

        required = [
            str(norad).strip()
            for norad in norad_ids
        ]

        try:

            analysis = (
                self.analyze_tle_file(
                    file_path
                )
            )

            available = set(
                analysis["norad_ids"]
            )

            epochs = analysis["epochs"]

        except Exception:

            return []

        return [

            norad

            for norad in required

            if (
                norad in available
                and
                norad in epochs
            )

        ]


    def get_library_diagnostics(
        self,
        norad_ids
    ):

        required = [
            str(norad).strip()
            for norad in norad_ids
        ]

        files = self.get_user_tle_files()

        if not files:

            return (
                "Automatic TLE selection failed.\n\n"
                "No TLE files were found in:\n"
                f"{self.USER_TLE_DIRECTORY}\n\n"
                "Please pull TLE data from CelesTrak "
                "or Space-Track, or import a TLE file."
            )

        lines = [

            "Automatic TLE selection failed.",

            "",

            "No local TLE file contained any of "
            "the requested satellites.",

            "",

            "Required NORAD IDs:",

            ", ".join(required),

            "",

            "TLE files checked:",

        ]

        for file_path in files:

            try:

                analysis = (
                    self.analyze_tle_file(
                        file_path
                    )
                )

                available = set(
                    analysis["norad_ids"]
                )

                found = (
                    set(required)
                    & available
                )

                missing = (
                    set(required)
                    - available
                )

                lines.append(
                    f"  {file_path.name}"
                )

                lines.append(
                    "    Available: "
                    +
                    (
                        ", ".join(
                            sorted(found)
                        )
                        if found
                        else "None"
                    )
                )

                lines.append(
                    "    Missing: "
                    +
                    (
                        ", ".join(
                            sorted(missing)
                        )
                        if missing
                        else "None"
                    )
                )

            except Exception as error:

                lines.append(
                    f"  {file_path.name}: "
                    f"could not be read ({error})"
                )

        return "\n".join(lines)


    def create_tle_info(
        self,
        file_path,
        source,
        mode
    ):

        path = Path(
            file_path
        )

        self.current_file = path
        self.current_source = source
        self.current_mode = mode

        age = (
            self.get_file_age_hours(
                path
            )
        )

        epochs = (
            self.get_tle_epochs(
                path
            )
        )

        return {

            "file":
                path,

            "source":
                source,

            "mode":
                mode,

            "selection":
                mode,

            "age_hours":
                age,

            "tle_datetime":
                self.get_representative_tle_epoch(
                    path,
                    list(epochs.keys())
                ),

            "satellite_epochs":
                epochs,

            "available_satellites":
                list(epochs.keys()),

            "missing_satellites":
                [],

        }


    def identify_source(
        self,
        file_path
    ):

        name = (
            Path(file_path)
            .name
            .lower()
        )

        if name.startswith(
            "celestrak_"
        ):

            return "CelesTrak"

        if (
            name.startswith(
                "space_track_"
            )
            or
            name.startswith(
                "spacetrack_"
            )
        ):

            return "Space-Track"

        if name.startswith(
            "manual_"
        ):

            return "Manual"

        return "TLE Library"


    def get_status(
        self
    ):

        if self.current_file is None:

            return {

                "file": None,
                "source": None,
                "mode": "Automatic",
                "age_hours": None,
                "recent": False,

            }

        age = (
            self.get_file_age_hours(
                self.current_file
            )
        )

        return {

            "file":
                self.current_file,

            "source":
                self.current_source,

            "mode":
                self.current_mode,

            "age_hours":
                age,

            "recent":
                (
                    age is not None
                    and
                    age <= self.MAX_TLE_AGE_HOURS
                ),

        }
