# rating.py

K_FACTOR = 32  # 점수 변동 폭 (높을수록 승패에 따른 점수 변화가 큼)

# 기본 K=32, 배치고사(신규) K=64
def get_k_factor(matches_played: int) -> int:
    if matches_played < 10:
        return 64  # 초반 10판은 점수가 크게 변동됨 (빠른 수렴)
    return 32      # 이후에는 안정적으로 변동

def calculate_expected_score(rating_a: float, rating_b: float) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

def update_elo(rating_a: float, rating_b: float, result: float, matches_a: int, matches_b: int):
    """
    matches_a, matches_b 인자가 추가되었습니다.
    """
    expected_a = calculate_expected_score(rating_a, rating_b)
    expected_b = calculate_expected_score(rating_b, rating_a)

    # 각자 자신의 경기 수에 맞춰 K-Factor 적용
    k_a = get_k_factor(matches_a)
    k_b = get_k_factor(matches_b)

    new_rating_a = rating_a + k_a * (result - expected_a)
    new_rating_b = rating_b + k_b * ((1 - result) - expected_b)

    return new_rating_a, new_rating_b