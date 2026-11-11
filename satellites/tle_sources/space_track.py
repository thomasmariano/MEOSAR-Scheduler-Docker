import requests


class SpaceTrackSource:

    BASE_URL = (
        "https://www.space-track.org"
    )

    LOGIN_URL = (
        f"{BASE_URL}/ajaxauth/login"
    )

    TLE_URL = (
        f"{BASE_URL}/basicspacedata/query"
    )

    REQUEST_TIMEOUT = 30


    # ==========================================================
    # INITIALIZATION
    # ==========================================================

    def __init__(
        self,
        username,
        password
    ):

        self.username = (
            username.strip()
            if username
            else ""
        )

        self.password = (
            password
            if password
            else ""
        )

        self.session = (
            requests.Session()
        )

        self.logged_in = False


    # ==========================================================
    # LOGIN
    # ==========================================================

    def login(self):

        if not self.username:

            raise ValueError(
                "Space-Track username is required."
            )

        if not self.password:

            raise ValueError(
                "Space-Track password is required."
            )


        try:

            response = (
                self.session.post(

                    self.LOGIN_URL,

                    data={
                        "identity": self.username,
                        "password": self.password,
                    },

                    timeout=self.REQUEST_TIMEOUT

                )
            )

        except requests.RequestException as error:

            raise RuntimeError(

                "Unable to connect to Space-Track "
                "during login.\n\n"

                f"{error}"

            )


        if response.status_code != 200:

            raise RuntimeError(

                "Space-Track login failed.\n\n"

                f"HTTP Status: "
                f"{response.status_code}\n\n"

                "Server response:\n"

                f"{response.text[:1000]}"

            )


        response_text = (
            response.text.strip()
        )

        lowered = (
            response_text.lower()
        )


        if (
            "login failed"
            in
            lowered
        ):

            raise RuntimeError(

                "Space-Track rejected the login.\n\n"

                f"Server response:\n"
                f"{response_text[:1000]}"

            )


        if (
            "incorrect"
            in
            lowered
        ):

            raise RuntimeError(

                "Space-Track rejected the login credentials.\n\n"

                f"Server response:\n"
                f"{response_text[:1000]}"

            )


        self.logged_in = True


    # ==========================================================
    # VALIDATE SINGLE TLE
    # ==========================================================

    @staticmethod
    def validate_tle_response(
        tle_data,
        norad_id
    ):

        if not tle_data:

            raise ValueError(

                "Space-Track returned an empty response "
                f"for NORAD {norad_id}."

            )


        lines = [

            line.strip()

            for line in tle_data.splitlines()

            if line.strip()

        ]


        line1 = None
        line2 = None


        for line in lines:

            if line.startswith("1 "):

                line1 = line

            elif line.startswith("2 "):

                line2 = line


        if line1 is None or line2 is None:

            raise ValueError(

                "Space-Track did not return a valid "
                f"TLE for NORAD {norad_id}.\n\n"

                "Server response:\n"

                f"{tle_data[:1500]}"

            )


        returned_norad = (
            line1[2:7].strip()
        )

        requested_norad = (
            str(norad_id).strip()
        )


        if returned_norad != requested_norad:

            raise ValueError(

                "Space-Track returned the wrong "
                "NORAD object.\n\n"

                f"Requested: {requested_norad}\n"
                f"Returned:  {returned_norad}"

            )


        return (
            line1
            + "\n"
            + line2
        )


    # ==========================================================
    # FETCH ONE SATELLITE
    # ==========================================================

    def fetch_satellite(
        self,
        norad_id
    ):

        if not self.logged_in:

            self.login()


        norad_id = str(
            norad_id
        ).strip()


        if not norad_id:

            raise ValueError(
                "Invalid NORAD ID."
            )


        query = (

            "class/gp/"
            f"NORAD_CAT_ID/{norad_id}/"
            "format/tle"

        )


        url = (
            self.TLE_URL
            + "/"
            + query
        )


        try:

            response = (
                self.session.get(

                    url,

                    timeout=self.REQUEST_TIMEOUT

                )
            )

        except requests.RequestException as error:

            raise RuntimeError(

                "Unable to connect to Space-Track "
                f"while requesting NORAD {norad_id}.\n\n"

                f"{error}"

            )


        if response.status_code == 204:

            raise RuntimeError(

                "Space-Track returned no TLE data "
                f"for NORAD {norad_id}."

            )


        if response.status_code != 200:

            raise RuntimeError(

                "Space-Track TLE request failed.\n\n"

                f"NORAD: {norad_id}\n"
                f"HTTP Status: "
                f"{response.status_code}\n\n"

                "Server response:\n"

                f"{response.text[:1500]}"

            )


        return self.validate_tle_response(

            response.text.strip(),

            norad_id

        )


    # ==========================================================
    # FETCH MULTIPLE SATELLITES
    # ==========================================================

    def fetch_tle_data(
        self,
        norad_ids
    ):

        if not norad_ids:

            raise ValueError(
                "No NORAD IDs were provided."
            )


        if not self.logged_in:

            self.login()


        # ------------------------------------------------------
        # Normalize and remove duplicates
        # ------------------------------------------------------

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


        if not normalized_ids:

            raise ValueError(
                "No valid NORAD IDs were provided."
            )


        # ------------------------------------------------------
        # Space-Track allows multiple NORAD IDs in one query.
        #
        # Example:
        #
        # class/gp/
        # NORAD_CAT_ID/41859,40589,25544/
        # format/tle
        # ------------------------------------------------------

        norad_query = (
            ",".join(
                normalized_ids
            )
        )


        query = (

            "class/gp/"
            f"NORAD_CAT_ID/{norad_query}/"
            "format/tle"

        )


        url = (
            self.TLE_URL
            + "/"
            + query
        )


        try:

            response = (
                self.session.get(

                    url,

                    timeout=self.REQUEST_TIMEOUT

                )
            )

        except requests.RequestException as error:

            raise RuntimeError(

                "Unable to connect to Space-Track "
                "while requesting TLE data.\n\n"

                f"{error}"

            )


        # ------------------------------------------------------
        # NO CONTENT
        # ------------------------------------------------------

        if response.status_code == 204:

            raise RuntimeError(

                "Space-Track returned no TLE data "
                "for the requested satellites.\n\n"

                f"Requested NORAD IDs:\n"
                f"{', '.join(normalized_ids)}"

            )


        # ------------------------------------------------------
        # HTTP ERROR
        # ------------------------------------------------------

        if response.status_code != 200:

            raise RuntimeError(

                "Space-Track TLE request failed.\n\n"

                f"HTTP Status: "
                f"{response.status_code}\n\n"

                f"Requested NORAD IDs:\n"
                f"{', '.join(normalized_ids)}\n\n"

                "Server response:\n"

                f"{response.text[:2000]}"

            )


        tle_data = (
            response.text.strip()
        )


        if not tle_data:

            raise RuntimeError(

                "Space-Track returned an empty "
                "TLE response.\n\n"

                f"Requested NORAD IDs:\n"
                f"{', '.join(normalized_ids)}"

            )


        # ------------------------------------------------------
        # Parse the returned TLEs.
        #
        # Space-Track format/tle returns two-line
        # element sets. There may be several pairs.
        # ------------------------------------------------------

        lines = [

            line.strip()

            for line in tle_data.splitlines()

            if line.strip()

        ]


        tle_blocks = []

        current_line1 = None


        for line in lines:

            if line.startswith("1 "):

                current_line1 = line

                continue


            if (
                line.startswith("2 ")
                and
                current_line1 is not None
            ):

                tle_blocks.append(

                    (
                        current_line1,
                        line
                    )

                )

                current_line1 = None


        # ------------------------------------------------------
        # Make sure Space-Track actually returned TLEs.
        # ------------------------------------------------------

        if not tle_blocks:

            raise RuntimeError(

                "Space-Track returned data, but it "
                "did not contain valid TLE line pairs.\n\n"

                "Server response:\n"

                f"{tle_data[:2000]}"

            )


        # ------------------------------------------------------
        # Index returned TLEs by NORAD ID.
        # ------------------------------------------------------

        returned_tles = {}


        for line1, line2 in tle_blocks:

            returned_norad = (
                line1[2:7].strip()
            )

            returned_tles[
                returned_norad
            ] = (

                line1
                + "\n"
                + line2

            )


        # ------------------------------------------------------
        # Determine which requested satellites are missing.
        # ------------------------------------------------------

        missing_ids = [

            norad_id

            for norad_id in normalized_ids

            if norad_id not in returned_tles

        ]


        if missing_ids:

            raise RuntimeError(

                "Space-Track did not return TLE data "
                "for all requested satellites.\n\n"

                f"Missing NORAD IDs:\n"
                f"{', '.join(missing_ids)}\n\n"

                f"Returned NORAD IDs:\n"
                f"{', '.join(sorted(returned_tles.keys()))}"

            )


        # ------------------------------------------------------
        # Rebuild output in the same order requested by GUI.
        # ------------------------------------------------------

        blocks = [

            returned_tles[norad_id]

            for norad_id in normalized_ids

        ]


        return (
            "\n".join(
                blocks
            )
            + "\n"
        )


    # ==========================================================
    # CLOSE
    # ==========================================================

    def close(self):

        self.session.close()

        self.logged_in = False