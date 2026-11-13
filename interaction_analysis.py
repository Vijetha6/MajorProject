def analyze_medicine_interactions(current_medicines, new_medicines):
    """Return an explicit unavailable result until a verified source is configured."""
    return {
        "status": "unavailable",
        "message": (
            "No verified medicine-interaction knowledge source is configured. "
            "Interactions could not be assessed; this is not a finding of no interaction."
        ),
        "warnings": [],
        "sources": [],
        "current_medicines_received": len(current_medicines),
        "new_medicines_received": len(new_medicines),
    }
