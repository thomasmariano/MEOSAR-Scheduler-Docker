# core/scoring.py

def calculate_score(
    goddard_view,
    mission_view
):
    """
    Calculate the satellite tracking score.

    The score is based on equal weighting of:
        - Goddard elevation
        - Mission-site elevation

    A satellite that is not mutually visible receives a score of 0.
    """

    if not goddard_view["visible"]:
        return 0

    if not mission_view["visible"]:
        return 0

    goddard_elevation = goddard_view["elevation_deg"]
    mission_elevation = mission_view["elevation_deg"]

    score = (
        0.50 * mission_elevation
        +
        0.50 * goddard_elevation
    )

    return score