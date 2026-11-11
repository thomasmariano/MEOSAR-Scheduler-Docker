"""Records responsibilities extracted from the public TLE manager."""
from datetime import datetime, timezone, timedelta
from pathlib import Path


class TLERecordsMixin:
    @staticmethod
    def read_tle_lines(
        file_path
    ):

        file_path = Path(
            file_path
        )

        try:

            text = file_path.read_text(
                encoding="utf-8-sig"
            )

        except UnicodeDecodeError:

            text = file_path.read_text(
                encoding="latin-1"
            )

        return [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]


    @staticmethod
    def analyze_tle_file(file_path):
        from satellites.tle_manager import TLEManager
        from skyfield.api import EarthSatellite, load
        path=Path(file_path)
        if not path.is_file(): raise FileNotFoundError(f"TLE file not found: {path}")
        lines=TLEManager.read_tle_lines(path)
        pairs=[]; epochs={}; warnings=[]
        ts=load.timescale(builtin=True)
        for index,line1 in enumerate(lines):
            if not line1.startswith("1 "): continue
            if index+1>=len(lines):
                warnings.append(f"Line {index+1}: missing line 2");continue
            line2=lines[index+1]
            if (len(line1)<63 or len(line2)<63 or not line2.startswith("2 ") or line1[2:7]!=line2[2:7]):
                warnings.append(f"Line {index+1}: incomplete/mismatched pair");continue
            try:
                sat=EarthSatellite(line1,line2,ts=ts)
                norad=str(sat.model.satnum)
                epoch=sat.epoch.utc_datetime()
                if not 0<sat.model.ecco<1 and sat.model.ecco!=0: raise ValueError("invalid eccentricity")
                if sat.model.no_kozai<=0: raise ValueError("invalid mean motion")
                pairs.append((norad,line1,line2))
                if norad not in epochs or epoch>epochs[norad]:epochs[norad]=epoch
            except (ValueError,TypeError,OverflowError) as exc:
                warnings.append(f"Line {index+1}: {exc}")
        if not pairs: raise ValueError(f"No usable TLE pairs in {path.name}")
        return dict(file=path,valid=True,norad_ids=sorted(epochs),epochs=epochs,tle_pairs=pairs,warnings=warnings)


    @staticmethod
    def validate_tle_file(
        file_path
    ):

        from satellites.tle_manager import TLEManager
        analysis = (
            TLEManager.analyze_tle_file(
                file_path
            )
        )

        return analysis["valid"]


    @staticmethod
    def get_norad_ids(
        file_path
    ):

        from satellites.tle_manager import TLEManager
        analysis = (
            TLEManager.analyze_tle_file(
                file_path
            )
        )

        return list(
            analysis["norad_ids"]
        )


    @staticmethod
    def get_tle_pairs(
        file_path
    ):

        from satellites.tle_manager import TLEManager
        analysis = (
            TLEManager.analyze_tle_file(
                file_path
            )
        )

        return list(
            analysis["tle_pairs"]
        )


    @staticmethod
    def get_tle_epoch(
        line1
    ):

        line1 = line1.strip()

        if not line1.startswith("1 "):

            raise ValueError(
                "Invalid TLE line 1."
            )

        if len(line1) < 32:

            raise ValueError(
                "TLE line 1 is too short."
            )

        epoch_text = line1[18:32].strip()

        if not epoch_text:

            raise ValueError(
                "TLE epoch is missing."
            )

        try:

            year_short = int(
                epoch_text[:2]
            )

            day_of_year = float(
                epoch_text[2:]
            )

        except ValueError:

            raise ValueError(
                f"Invalid TLE epoch: {epoch_text}"
            )

        if year_short >= 57:

            year = 1900 + year_short

        else:

            year = 2000 + year_short

        return (
            datetime(
                year,
                1,
                1,
                tzinfo=timezone.utc
            )
            + timedelta(
                days=day_of_year - 1
            )
        )


    @staticmethod
    def get_tle_epochs(
        file_path
    ):

        from satellites.tle_manager import TLEManager
        analysis = (
            TLEManager.analyze_tle_file(
                file_path
            )
        )

        return dict(
            analysis["epochs"]
        )


    @staticmethod
    def get_representative_tle_epoch(
        file_path,
        norad_ids
    ):

        from satellites.tle_manager import TLEManager
        analysis = (
            TLEManager.analyze_tle_file(
                file_path
            )
        )

        epochs = analysis["epochs"]

        required = [
            str(norad).strip()
            for norad in norad_ids
        ]

        selected_epochs = [

            epochs[norad]

            for norad in required

            if norad in epochs

        ]

        if not selected_epochs:

            return None

        timestamps = [

            epoch.timestamp()

            for epoch in selected_epochs

        ]

        average_timestamp = (
            sum(timestamps)
            / len(timestamps)
        )

        return datetime.fromtimestamp(
            average_timestamp,
            tz=timezone.utc
        )


    @staticmethod
    def get_tle_event_difference(
        file_path,
        norad_ids,
        target_datetime
    ):

        from satellites.tle_manager import TLEManager
        if target_datetime is None:

            return None

        if target_datetime.tzinfo is None:

            target_datetime = (
                target_datetime.replace(
                    tzinfo=timezone.utc
                )
            )

        else:

            target_datetime = (
                target_datetime.astimezone(
                    timezone.utc
                )
            )

        analysis = (
            TLEManager.analyze_tle_file(
                file_path
            )
        )

        epochs = analysis["epochs"]

        required = [
            str(norad).strip()
            for norad in norad_ids
        ]

        if not required:

            return None

        differences = []
        satellite_epochs = {}
        missing_satellites = []

        for norad_id in required:

            epoch = epochs.get(
                norad_id
            )

            if epoch is None:

                missing_satellites.append(
                    norad_id
                )

                continue

            difference = abs(
                target_datetime - epoch
            )

            differences.append(
                (
                    difference,
                    norad_id,
                    epoch
                )
            )

            satellite_epochs[norad_id] = epoch

        if not differences:

            return {

                "max_difference":
                    None,

                "average_difference":
                    None,

                "worst_norad_id":
                    None,

                "worst_epoch":
                    None,

                "satellite_epochs":
                    satellite_epochs,

                "missing_satellites":
                    missing_satellites,

            }

        worst = max(
            differences,
            key=lambda item: (
                item[0],
                item[1]
            )
        )

        average_difference = (
            sum(
                (
                    item[0]
                    for item in differences
                ),
                timedelta(0)
            )
            / len(differences)
        )

        return {

            "max_difference":
                worst[0],

            "average_difference":
                average_difference,

            "worst_norad_id":
                worst[1],

            "worst_epoch":
                worst[2],

            "satellite_epochs":
                satellite_epochs,

            "missing_satellites":
                missing_satellites,

        }

