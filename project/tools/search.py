import os

import requests


SEARCH_URL = "https://google.serper.dev/search"


def search_web(query: str) -> dict:
    api_key = os.getenv("SERPER_API_KEY")
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": 5,
    }

    try:
        response = requests.post(
            SEARCH_URL,
            headers=headers,
            json=payload,
            timeout=5,
        )
        response.raise_for_status()

        data = response.json()
        organic_results = data.get("organic", [])
        results = [
            {
                "title": item.get("title"),
                "snippet": item.get("snippet"),
                "link": item.get("link"),
            }
            for item in organic_results[:3]
        ]

        if not results:
            return {
                "query": query,
                "results": [],
                "message": "No results found for this query",
            }

        return {
            "query": query,
            "results": results,
        }
    except requests.exceptions.Timeout:
        return {"error": "Search service timed out"}
    except Exception:
        return {"error": "Search service unavailable"}
