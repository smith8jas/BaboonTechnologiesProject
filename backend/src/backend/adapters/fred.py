from backend.core.config import settings
import requests


_cache: float | None = None

def fetch_risk_free_rate() -> float:
    global _cache
    if _cache is None:
        response = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": "DGS10",
                "api_key": settings.fred_api_key,
                "sort_order": "desc",
                "limit": 1,
                "file_type": "json",
            }
        )
        _cache = float(response.json()["observations"][0]["value"]) / 100
    return _cache