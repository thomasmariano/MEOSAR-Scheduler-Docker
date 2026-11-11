"""Downloads responsibilities extracted from the public TLE manager."""



class TLEDownloadsMixin:
    def download_celestrak(
        self,
        norad_ids
    ):

        from ..tle_sources.celestrak import (
            CelesTrakSource
        )

        source = CelesTrakSource()

        try:

            result = (
                source.fetch_tle_data(
                    norad_ids
                )
            )

        finally:

            source.close()

        tle_data = result["tle_data"]

        file_path = (
            self.save_downloaded_tle(
                tle_data,
                "CelesTrak"
            )
        )

        return self.create_tle_info(
            file_path,
            "CelesTrak",
            "CelesTrak"
        )


    def download_space_track(
        self,
        norad_ids,
        username,
        password
    ):

        from ..tle_sources.space_track import (
            SpaceTrackSource
        )

        source = SpaceTrackSource(
            username=username,
            password=password
        )

        try:

            tle_data = (
                source.fetch_tle_data(
                    norad_ids
                )
            )

        finally:

            source.close()

        file_path = (
            self.save_downloaded_tle(
                tle_data,
                "Space-Track"
            )
        )

        return self.create_tle_info(
            file_path,
            "Space-Track",
            "Space-Track"
        )

