
import os
import time
import requests
import datetime
import logging
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Granite API endpoint (e.g., provided by your Granite service)
GRANITE_ENDPOINT = os.getenv("GRANITE_ENDPOINT")
if not GRANITE_ENDPOINT:
    logger.error("GRANITE_ENDPOINT is not set. Exiting.")
    exit(1)

# GitHub token for GitHub API calls
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    logger.error("GITHUB_TOKEN is not set. Exiting.")
    exit(1)

def get_date_range():
    """
    Computes the start and end dates for last week.
    Last week is defined as:
      - Start: Previous Monday (7 days ago)
      - End: Previous Sunday (1 day ago)
    Returns:
        (start_date, end_date) as datetime.date objects.
    """
    today = datetime.datetime.now().date()
    last_week_start = today - datetime.timedelta(days=7)
    last_week_end = today - datetime.timedelta(days=1)
    logger.info(f"Calculated date range: {last_week_start} to {last_week_end}")
    return last_week_start, last_week_end

def fetch_all_prs_by_user(username, start_date, end_date):
    """
    Fetches all pull requests created by the given user across all repositories
    within the specified date range using the GitHub search API.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {GITHUB_TOKEN}"
    }
    query = f"is:pr author:{username} created:{start_date}..{end_date}"
    url = "https://api.github.com/search/issues"
    prs = []
    page = 1
    per_page = 100
    while True:
        params = {"q": query, "per_page": per_page, "page": page}
        logger.info(f"Fetching page {page} of PRs for user {username} with query: {query}")
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 403:
            logger.warning("Rate limit exceeded. Sleeping for 60 seconds...")
            time.sleep(60)
            continue
        elif response.status_code != 200:
            logger.error(f"Error fetching PRs: {response.status_code} {response.text}")
            break
        data = response.json()
        items = data.get("items", [])
        logger.debug(f"Retrieved {len(items)} PRs on page {page}.")
        prs.extend(items)
        if len(items) < per_page:
            logger.info("Last page reached.")
            break
        page += 1
    logger.info(f"Total PRs fetched: {len(prs)}")
    return prs

def get_pr_status(pr):
    """
    Determines the status of a pull request.
    Returns one of: "open", "closed", or "merged".
    """
    pr_number = pr.get("number", "unknown")
    status = pr.get("state", "unknown")
    logger.debug(f"PR #{pr_number}: Initial state is '{status}'.")
    if status == "closed" and "pull_request" in pr:
        pr_url = pr["pull_request"].get("url")
        if pr_url:
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": f"token {GITHUB_TOKEN}"
            }
            resp = requests.get(pr_url, headers=headers)
            if resp.status_code == 200:
                pr_details = resp.json()
                if pr_details.get("merged_at"):
                    logger.debug(f"PR #{pr_number} is merged.")
                    return "merged"
                else:
                    logger.debug(f"PR #{pr_number} is closed but not merged.")
                    return "closed"
            else:
                logger.warning(f"Failed to get detailed status for PR #{pr_number}. Returning 'closed'.")
                return "closed"
    logger.debug(f"PR #{pr_number}: Final status is '{status}'.")
    return status

def generate_pr_detailed_summary(pr):
    """
    Uses the Granite-8B-Code-Instruct-128k API to generate a detailed summary for a single PR.
    """
    pr_number = pr.get("number", "unknown")
    title = pr.get("title", "No title")
    body = pr.get("body", "No description provided.")
    logger.info(f"Generating detailed summary for PR #{pr_number}: '{title}'")
    prompt = (
        "You are a knowledgeable code and workflow analyst. "
        "Summarize the following pull request in detail, highlighting its purpose, changes, and notable insights. "
        "Include any actionable observations.\n\n"
        f"Title: {title}\n\n"
        f"Body: {body}\n\n"
        "Detailed Summary:"
    )
    payload = {
        "model": "granite-8b-code-instruct-128k",
        "prompt": prompt,
        "max_tokens": 200,
        "temperature": 0.7
    }
    granite_token = os.getenv("GRANITE_TOKEN")
    if not granite_token:
        logger.error("GRANITE_TOKEN is not set. Exiting.")
        return ""
    headers_payload = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {granite_token}"
    }
    response = requests.post(GRANITE_ENDPOINT, headers=headers_payload, json=payload)
    if response.status_code == 200:
        data = response.json()
        summary = data.get("choices", [{}])[0].get("text", "").strip()
        logger.debug(f"Received detailed summary for PR #{pr_number}.")
        return summary
    else:
        logger.error(f"Error calling Granite API for PR #{pr_number}: {response.status_code} {response.text}")
        return ""

def generate_dashboard(prs, start_date, end_date):
    """
    Generates a Markdown-formatted dashboard for all PR items.
    Columns: Repo, PR Number (as a link), Title, Author, Created At, Status.
    """
    logger.info("Generating dashboard for all PRs...")
    md = f"# Weekly PR Dashboard\n\n"
    md += f"**Date Range:** {start_date} to {end_date}\n\n"
    if not prs:
        md += "No pull requests were created in this period.\n"
        return md

    md += ("| Repo | PR Number | Title | Author | Created At | Status |\n"
           "|------|-----------|-------|--------|------------|--------|\n")
    for pr in prs:
        repo_url = pr.get("repository_url", "")
        repo = "/".join(repo_url.split("/")[-2:]) if repo_url else "unknown"
        number = pr.get("number", "")
        pr_url = pr.get("html_url", "")
        title = pr.get("title", "").replace("|", "\\|")
        user = pr.get("user", {}).get("login", "unknown")
        created_at = pr.get("created_at", "")
        status = get_pr_status(pr)
        pr_number_link = f"[{number}]({pr_url})" if pr_url else str(number)
        md += f"| {repo} | {pr_number_link} | {title} | {user} | {created_at} | {status} |\n"
    logger.info("Dashboard generation complete.")
    return md

def generate_detailed_pr_summaries(prs):
    """
    Generates detailed summaries for each PR.
    Each PR is given its own heading with a detailed summary.
    """
    logger.info("Generating detailed summaries for each PR...")
    md = "\n# Detailed PR Summaries\n\n"
    for pr in prs:
        number = pr.get("number", "unknown")
        title = pr.get("title", "No Title")
        pr_url = pr.get("html_url", "")
        heading = f"## PR {number}: {title}"
        if pr_url:
            heading += f" ([Link]({pr_url}))"
        md += heading + "\n\n"
        detailed_summary = generate_pr_detailed_summary(pr)
        md += detailed_summary + "\n\n"
        md += "---\n\n"
        time.sleep(1)  # Pause to avoid rate limits
    logger.info("Detailed PR summaries generated.")
    return md

def main():
    username ="adamkaabyia" #"Shai1-Levi"
    logger.info(f"Starting PR dashboard generation for user: {username}")
    last_week_start, last_week_end = get_date_range()
    start_date_str = last_week_start.strftime("%Y-%m-%d")
    end_date_str = last_week_end.strftime("%Y-%m-%d")
    logger.info(f"Using date range: {start_date_str} to {end_date_str}")

    all_prs = fetch_all_prs_by_user(username, start_date_str, end_date_str)
    logger.info(f"Found {len(all_prs)} PRs by {username} in the given period.")

    # Generate the dashboard (user-specific)
    dashboard_md = generate_dashboard(all_prs, start_date_str, end_date_str)
    # Generate detailed summaries for each PR
    detailed_summaries_md = generate_detailed_pr_summaries(all_prs)

    # Overall Concise Summary (fixed text as requested)
    overall_concise_summary = (
        "# Overall Concise Summary\n\n"
        "The pull request is a part of a larger deployment process aimed at improving security and authentication for publishing site content.\n"
        "The changes made in the pull request focus on enhancing the user experience, improving readability, and ensuring the dashboard is secure and accessible to authorized users.\n"
        "The pull request has been merged and deployed, and the changes are now live on the test matrix dashboard.\n"
        "The pull request may require additional testing and documentation to ensure that the deployment process is working as expected and that only authorized users can publish updated site content.\n"
        "The pull request can be improved further by addressing any remaining bugs or incorporating new features that enhance the overall functionality of the dashboard.\n"
    )

    # Weekly PR Summary section
    weekly_summary_header = (
        "# Weekly PR Summary\n\n"
        f"**Date Range:** {start_date_str} to {end_date_str}\n\n"
        "## Summary by User\n\n"
    )
    # Generate a summary by user table
    user_counts = defaultdict(int)
    for pr in all_prs:
        user = pr.get("user", {}).get("login", "unknown")
        user_counts[user] += 1
    user_table = "| User | PR Count |\n|------|----------|\n"
    for user, count in user_counts.items():
        user_table += f"| {user} | {count} |\n"

    # Assemble final output with all sections:
    final_output = (
        overall_concise_summary + "\n" +
        weekly_summary_header + user_table + "\n" +
        dashboard_md + "\n" +
        detailed_summaries_md
    )

    output_filename = "dashboard.md"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(final_output)
    logger.info(f"Dashboard and detailed summaries stored in {output_filename}")

if __name__ == "__main__":
    main()