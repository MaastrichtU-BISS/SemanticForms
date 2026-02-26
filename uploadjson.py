import json
import requests


def uploadjson(filename, url):
    BASE_URL = url

    session = requests.Session()

    login_data = {
        "username": "developer",  # change if needed
        "password": "your_password"
    }
    session.post(f"{BASE_URL}/login", data=login_data)

    with open(filename, "rb") as f:
        files = {
            "instancefile": (filename, f, "application/ld+json")
        }

        response = session.post(f"{BASE_URL}/upload", files=files)

    print("Status:", response.status_code)
    print("Final URL:", response.url)
    print("Was redirected:", len(response.history) > 0)