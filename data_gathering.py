import time

import requests


def fetch_all_prs_by_user(username, start_date, end_date):
    """
    Fetches all pull requests created by the given user across all repositories
    within the specified date range using the GitHub search API.

    Args:
        username (str): GitHub username.
        start_date (str): Start date (YYYY-MM-DD).
        end_date (str): End date (YYYY-MM-DD).

    Returns:
        List of PR items.
    """
    headers = {"Accept": "application/vnd.github+json"}
    query = f"is:pr author:{username} created:{start_date}..{end_date}"
    url = "https://api.github.com/search/issues"
    prs = []
    page = 1
    per_page = 100
    while True:
        params = {"q": query, "per_page": per_page, "page": page}
        print(f"Fetching page {page} of PRs for user {username}...")
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 403:
            print("Rate limit exceeded. Sleeping for 60 seconds...")
            time.sleep(60)
            continue
        elif response.status_code != 200:
            print(f"Error fetching PRs: {response.status_code} {response.text}")
            break
        data = response.json()
        items = data.get("items", [])
        prs.extend(items)
        if len(items) < per_page:
            break
        page += 1
    return prs
