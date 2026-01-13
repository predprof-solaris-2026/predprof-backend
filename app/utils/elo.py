
def calculate_win_probability(player_rating: int, opponent_rating: int) -> float:
    rating_diff = opponent_rating - player_rating
    return 1 / (1 + 10 ** (rating_diff / 400))


def calculate_elo_change(player_rating: int, opponent_rating: int, score: float, k_factor: int = 32) -> int:
    expected_score = calculate_win_probability(player_rating, opponent_rating)
    elo_change = k_factor * (score - expected_score)
    return int(round(elo_change))


def update_ratings_after_match(
    p1_rating: int,
    p2_rating: int,
    outcome: str
) -> tuple[int, int]:
    if outcome == "p1_win":
        p1_score, p2_score = 1.0, 0.0
    elif outcome == "p2_win":
        p1_score, p2_score = 0.0, 1.0
    elif outcome == "draw":
        p1_score, p2_score = 0.5, 0.5
    else:
        raise ValueError(f"Invalid outcome: {outcome}")
    
    p1_change = calculate_elo_change(p1_rating, p2_rating, p1_score)
    p2_change = calculate_elo_change(p2_rating, p1_rating, p2_score)
    
    return p1_rating + p1_change, p2_rating + p2_change, p1_change, p2_change
