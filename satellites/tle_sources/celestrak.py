import requests


class CelesTrakSource:

    BASE_URL = (
        "https://celestrak.org/NORAD/elements/gp.php"
    )

    REQUEST_TIMEOUT = 30


    # ==========================================================
    # INITIALIZATION
    # ==========================================================

    def __init__(self):

        self.session = (
            requests.Session()
        )


    # ==========================================================
    # FETCH ONE SATELLITE
    # ==========================================================

    def fetch_satellite(
        self,
        norad_id
    ):

        norad_id = str(
            norad_id
        ).strip()

        try:

            response = self.session.get(

                self.BASE_URL,

                params={
                    "CATNR": norad_id,
                    "FORMAT": "tle",
                },

                timeout=self.REQUEST_TIMEOUT

            )

        except requests.RequestException as error:

            raise RuntimeError(

                f"Network error while requesting "
                f"NORAD {norad_id}:\n{error}"

            )


        if response.status_code != 200:

            raise RuntimeError(

                f"CelesTrak request failed.\n\n"
                f"NORAD: {norad_id}\n"
                f"HTTP Status: "
                f"{response.status_code}\n\n"
                f"Server response:\n"
                f"{response.text[:1500]}"

            )


        tle_data = (
            response.text.strip()
        )


        if not tle_data:

            raise ValueError(

                f"CelesTrak returned no TLE "
                f"for NORAD {norad_id}."

            )


        return tle_data


    # ==========================================================
    # FETCH MULTIPLE SATELLITES
    # ==========================================================

    def fetch_tle_data(
        self,
        norad_ids
    ):

        if not norad_ids:

            raise ValueError(
                "No satellite NORAD IDs were provided."
            )


        normalized_ids = []

        for norad_id in norad_ids:

            norad_id = str(
                norad_id
            ).strip()

            if (
                norad_id
                and
                norad_id not in normalized_ids
            ):

                normalized_ids.append(
                    norad_id
                )


        blocks = []

        successful_ids = []

        failed = []


        for norad_id in normalized_ids:

            try:

                tle_data = (
                    self.fetch_satellite(
                        norad_id
                    )
                )

                blocks.append(
                    tle_data
                )

                successful_ids.append(
                    norad_id
                )

            except Exception as error:

                failed.append(
                    {
                        "norad_id": norad_id,
                        "error": str(error),
                    }
                )


        # ------------------------------------------------------
        # Nothing worked
        # ------------------------------------------------------

        if not successful_ids:

            details = [
                "CelesTrak could not retrieve "
                "any requested TLEs.",
                "",
                "Failed satellites:",
            ]

            for item in failed:

                details.append(
                    f"  NORAD {item['norad_id']}: "
                    f"{item['error']}"
                )

            raise RuntimeError(
                "\n".join(details)
            )


        tle_data = (
            "\n".join(
                blocks
            )
            + "\n"
        )


        # ------------------------------------------------------
        # Return successful data AND failures.
        #
        # TLEManager will decide whether the file is
        # sufficient for the actual scheduler request.
        # ------------------------------------------------------

        return {

            "tle_data":
                tle_data,

            "successful_ids":
                successful_ids,

            "failed":
                failed,

        }


    # ==========================================================
    # CLOSE
    # ==========================================================

    def close(self):

        self.session.close()