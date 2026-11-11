# core/mission.py

from datetime import timedelta, timezone


class Mission:
    """
    Represents a MEOSAR mission and its scheduling window.
    """

    def __init__(
        self,
        name,
        location,
        event_time,
        hours_before,
        hours_after
    ):

        self.name = name
        self.location = location

        # Ensure event time is UTC-aware
        if event_time.tzinfo is None:
            event_time = event_time.replace(
                tzinfo=timezone.utc
            )

        self.event_time = event_time.astimezone(
            timezone.utc
        )

        self.hours_before = hours_before
        self.hours_after = hours_after

    def get_start_time(self):
        """
        Return the beginning of the mission scheduling window.
        """

        start = self.event_time - timedelta(
            hours=self.hours_before
        )

        return start.astimezone(timezone.utc)

    def get_end_time(self):
        """
        Return the end of the mission scheduling window.
        """

        end = self.event_time + timedelta(
            hours=self.hours_after
        )

        return end.astimezone(timezone.utc)

    def __str__(self):

        return (
            f"Mission: {self.name}\n"
            f"Event UTC: {self.event_time}\n"
            f"Window: "
            f"{self.get_start_time()} "
            f"to "
            f"{self.get_end_time()}"
        )