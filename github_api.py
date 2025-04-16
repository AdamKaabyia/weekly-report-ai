import time

from dotenv import load_dotenv
import os
import requests
from logger import logger

load_dotenv()

# GitHub token
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    logger.error("GITHUB_TOKEN is not set. Exiting.")
    exit(1)

def get_pr_status(pr):
    """Return 'open', 'closed', or 'merged' for a PR."""
    status = pr.get("state", "unknown")
    # If closed, check if merged
    if status == "closed" and "pull_request" in pr:
        pr_url = pr["pull_request"].get("url")
        if pr_url:
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": f"token {GITHUB_TOKEN}"
            }
            r = requests.get(pr_url, headers=headers)
            if r.status_code == 200:
                if r.json().get("merged_at"):
                    return "merged"
                else:
                    return "closed"
    return status


def get_authenticated_username():
    """Fetch GitHub username from the GitHub token."""
    url = "https://api.github.com/user"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {GITHUB_TOKEN}"
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        login = resp.json().get("login")
        if login:
            logger.info(f"Authenticated as: {login}")
            return login
    logger.error("Failed to fetch authenticated user from GitHub.")
    exit(1)



def fetch_all_prs_by_user(username, start_date, end_date):
    """Fetch all PRs for the user in the date range."""
    headers = {"Accept": "application/vnd.github+json",
               "Authorization": f"token {GITHUB_TOKEN}"}
    query = f"is:pr author:{username} created:{start_date}..{end_date}"
    url = "https://api.github.com/search/issues"
    prs = []
    page = 1
    per_page = 100

    while True:
        params = {"q": query, "per_page": per_page, "page": page}
        logger.info(f"Fetching page {page} with query: {query}")
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code == 403:
            logger.warning("GitHub rate limit exceeded. Sleeping 60s...")
            time.sleep(60)
            continue
        elif resp.status_code != 200:
            logger.error(f"Error fetching PRs: {resp.status_code} {resp.text}")
            break
        data = resp.json()
        items = data.get("items", [])
        prs.extend(items)
        if len(items) < per_page:
            logger.info("No more pages left.")
            break
        page += 1

    logger.info(f"Total PRs fetched: {len(prs)}")
    return prs
