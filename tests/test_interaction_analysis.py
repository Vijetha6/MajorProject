from interaction_analysis import analyze_medicine_interactions


def test_interaction_analysis_is_explicitly_unavailable_without_verified_source():
    result = analyze_medicine_interactions(["Medicine A"], ["Medicine B", "Medicine C"])

    assert result["status"] == "unavailable"
    assert "not a finding of no interaction" in result["message"]
    assert result["warnings"] == []
    assert result["sources"] == []
    assert result["current_medicines_received"] == 1
    assert result["new_medicines_received"] == 2
