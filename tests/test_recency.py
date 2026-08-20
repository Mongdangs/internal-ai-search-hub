from src.search.recency import recency_boost


def test_recency_boost_prefers_newer_file():
    mtimes = [100.0, 200.0]
    assert recency_boost(200.0, mtimes) > recency_boost(100.0, mtimes)
    assert recency_boost(200.0, mtimes) <= 1.15
