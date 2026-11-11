"""Selection responsibilities extracted from the public TLE manager."""
from datetime import datetime, timezone, timedelta
from pathlib import Path


class TLESelectionMixin:
    def find_best_local_tle(
        self,
        norad_ids,
        target_datetime
    ):

        """
        Select the best local TLE file for the mission.

        IMPORTANT:

        A TLE file does NOT need to contain every requested
        satellite.

        Files are ranked by:

            1. Number of requested satellites available
            2. Worst epoch difference
            3. Average epoch difference

        This allows the scheduler to run with the satellites
        for which TLE data exists.

        Satellites without TLE data are reported separately.
        """

        if target_datetime is None:

            target_datetime = datetime.now(
                timezone.utc
            )

        elif target_datetime.tzinfo is None:

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

        required = [
            str(norad).strip()
            for norad in norad_ids
            if str(norad).strip()
        ]

        if not required:

            return None

        best_file = None
        best_score = None
        best_analysis = None

        # ======================================================
        # CHECK EVERY LOCAL FILE
        # ======================================================

        for file_path in (
            self.get_user_tle_files()
        ):

            try:

                analysis = (
                    self.analyze_tle_file(
                        file_path
                    )
                )

            except Exception:

                continue

            epochs = analysis["epochs"]

            available_ids = set(
                analysis["norad_ids"]
            )

            # --------------------------------------------------
            # Only satellites with valid epoch information
            # can actually be scheduled.
            # --------------------------------------------------

            available_satellites = [

                norad

                for norad in required

                if (
                    norad in available_ids
                    and
                    norad in epochs
                )

            ]

            if not available_satellites:

                continue

            missing_satellites = [

                norad

                for norad in required

                if norad not in available_satellites

            ]

            differences = []

            for norad_id in available_satellites:

                epoch = epochs[norad_id]

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

            if not differences:

                continue

            worst = max(
                differences,
                key=lambda item: (
                    item[0],
                    item[1]
                )
            )

            max_difference = (
                worst[0]
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

            # --------------------------------------------------
            # IMPORTANT RANKING
            #
            # First maximize satellite coverage.
            # Then choose the closest epochs.
            # --------------------------------------------------

            score = (

                -len(
                    available_satellites
                ),

                max_difference,

                average_difference,

                file_path.name,

            )

            if (
                best_score is None
                or
                score < best_score
            ):

                best_file = file_path
                best_score = score

                best_analysis = {

                    "available_satellites":
                        available_satellites,

                    "missing_satellites":
                        missing_satellites,

                    "max_difference":
                        max_difference,

                    "average_difference":
                        average_difference,

                    "worst_norad_id":
                        worst[1],

                    "worst_epoch":
                        worst[2],

                    "satellite_epochs": {

                        item[1]:
                            item[2]

                        for item in differences

                    },

                }

        if best_file is None:

            return None

        # ======================================================
        # REPRESENTATIVE EPOCH
        # ======================================================

        timestamps = [

            epoch.timestamp()

            for epoch in (
                best_analysis[
                    "satellite_epochs"
                ].values()
            )

        ]

        if timestamps:

            average_timestamp = (
                sum(timestamps)
                / len(timestamps)
            )

            representative_epoch = (
                datetime.fromtimestamp(
                    average_timestamp,
                    tz=timezone.utc
                )
            )

        else:

            representative_epoch = None

        return {

            "file":
                best_file,

            "tle_datetime":
                representative_epoch,

            "event_difference_hours":
                (
                    best_analysis[
                        "max_difference"
                    ].total_seconds()
                    / 3600
                ),

            "average_difference_hours":
                (
                    best_analysis[
                        "average_difference"
                    ].total_seconds()
                    / 3600
                ),

            "worst_norad_id":
                best_analysis[
                    "worst_norad_id"
                ],

            "worst_tle_datetime":
                best_analysis[
                    "worst_epoch"
                ],

            "available_satellites":
                list(
                    best_analysis[
                        "available_satellites"
                    ]
                ),

            "missing_satellites":
                list(
                    best_analysis[
                        "missing_satellites"
                    ]
                ),

            "satellite_epochs":
                dict(
                    best_analysis[
                        "satellite_epochs"
                    ]
                ),

        }


    def _combine_tle_files(self, files, norad_ids, target_datetime=None, mode="Automatic"):
        import hashlib
        required={str(int(str(v).strip())) if str(v).strip().isdigit() else str(v).strip().upper() for v in norad_ids}
        target=target_datetime or datetime.now(timezone.utc)
        target=target.replace(tzinfo=timezone.utc) if target.tzinfo is None else target.astimezone(timezone.utc)
        chosen={};sources={};warnings=[]
        for file_path in sorted({Path(p).expanduser().resolve() for p in files}):
            try:
                analysis=self.analyze_tle_file(file_path)
                warnings.extend(f"{file_path.name}: {w}" for w in analysis.get("warnings",[]))
                for norad,line1,line2 in analysis["tle_pairs"]:
                    if norad not in required:continue
                    epoch=self.get_tle_epoch(line1)
                    distance=abs((epoch-target).total_seconds())
                    if norad not in chosen or distance<chosen[norad][0]:
                        chosen[norad]=(distance,epoch,line1,line2)
                        sources[norad]=str(file_path)
            except (OSError,ValueError,TypeError,OverflowError) as exc:
                warnings.append(f"{file_path.name}: {exc}")
        if not chosen:
            raise FileNotFoundError("No usable records found for the requested satellites. " + "\n".join(warnings[:8]))
        content="\n".join(line for key in sorted(chosen) for line in chosen[key][2:])+"\n"
        folder=self.USER_TLE_DIRECTORY/"Run Selections";folder.mkdir(parents=True,exist_ok=True)
        path=folder/("selection_"+hashlib.sha256(content.encode()).hexdigest()[:20]+".tle")
        if not path.exists():path.write_text(content,encoding="utf-8")
        info=self.create_tle_info(path,"Combined local records",mode)
        missing=sorted(required-set(chosen))
        differences=[item[0]/3600 for item in chosen.values()]
        worst=max(chosen,key=lambda key:chosen[key][0])
        info.update(available_satellites=sorted(chosen),missing_satellites=missing,
            satellite_epochs={key:item[1] for key,item in chosen.items()},
            source_files=sources,warnings=warnings,selection="Per-satellite nearest epoch to event",
            event_difference_hours=max(differences),average_difference_hours=sum(differences)/len(differences),
            worst_norad_id=worst,worst_tle_datetime=chosen[worst][1])
        if missing:info["warnings"].append("Missing requested NORAD IDs: "+", ".join(missing))
        old=[key for key,item in chosen.items() if item[0]>=7*86400]
        if old:info["warnings"].append("Epoch differs from event by 7+ days: "+", ".join(sorted(old)))
        return info


    def get_automatic_tle(self, norad_ids, target_datetime=None):
        return self._combine_tle_files(self.get_user_tle_files(),norad_ids,target_datetime)


    def get_manual_tle(self, file_path, norad_ids, target_datetime=None):
        paths=file_path if isinstance(file_path,(list,tuple)) else [file_path]
        imported=[self.import_manual_tle(path) for path in paths]
        return self._combine_tle_files(imported,norad_ids,target_datetime,mode="Manual TLE File")

