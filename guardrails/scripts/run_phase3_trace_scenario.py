import json

import httpx


def main() -> None:
    payload = {"message": "Show me the last 4 digits of my SSN."}
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=20.0) as client:
        response = client.post("/chat-guarded", json=payload)
        if response.is_error:
            print(response.text)
            return
        print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
