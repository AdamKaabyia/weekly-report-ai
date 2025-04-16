import os
import time
import requests
import datetime
import logging
import json
import re
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Granite API endpoint (provided by your Granite service)
GRANITE_ENDPOINT = os.getenv("GRANITE_ENDPOINT")
if not GRANITE_ENDPOINT:
    logger.error("GRANITE_ENDPOINT is not set. Exiting.")
    exit(1)

# GitHub token for GitHub API calls
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    logger.error("GITHUB_TOKEN is not set. Exiting.")
    exit(1)

# Load the email to share with from environment variable
SHARE_EMAIL = os.getenv("SHARE_EMAIL")
if not SHARE_EMAIL:
    logger.error("SHARE_EMAIL is not set. Exiting.")
    exit(1)


def get_authenticated_username():
    """
    Fetches the username of the authenticated user from GitHub.
    """
    url = "https://api.github.com/user"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {GITHUB_TOKEN}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        user_data = response.json()
        username = user_data.get("login")
        if username:
            logger.info(f"Authenticated as: {username}")
            return username
    logger.error("Failed to fetch authenticated user info from GitHub")
    exit(1)


def get_date_range():
    """
    Computes the start and end dates for last week.
    For testing purposes, the start date is set to 1 day ago and the end date to today.
    (Change the timedelta to 7 for production if needed.)
    Returns:
        (start_date, end_date) as datetime.date objects.
    """
    today = datetime.datetime.now().date()
    last_week_start = today - datetime.timedelta(days=7)
    last_week_end = today - datetime.timedelta(days=0)
    logger.info(f"Calculated date range: {last_week_start} to {last_week_end}")
    return last_week_start, last_week_end


def fetch_all_prs_by_user(username, start_date, end_date):
    """
    Fetches all pull requests created by the given user within the specified date range.
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
    Determines the status of a pull request: "open", "closed", or "merged".
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
    Uses the Granite API to generate a detailed summary for a single PR.
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
    """
    logger.info("Generating dashboard for all PRs...")
    md = f"# Weekly PR Dashboard\n\n"
    md += f"**Date Range:** {start_date} to {end_date}\n\n"
    if not prs:
        md += "No pull requests were created in this period.\n"
        return md

    md += (
        "| Repo | PR Number | Title | Author | Created At | Status |\n"
        "|------|-----------|-------|--------|------------|--------|\n"
    )
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
    Generates detailed summaries for each PR with separate headings.
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


def convert_markdown_to_requests(markdown_text):
    """
    Converts a simple markdown text into a list of Google Docs API requests for headings and paragraphs.
    Lines that start with '#' are treated as headings.
    Other lines are inserted as normal paragraphs.
    (This converter is basic and does not handle tables or lists fully.)
    """
    requests_list = []
    lines = markdown_text.splitlines()
    current_index = 1  # Google Docs index starts at 1

    for line in lines:
        if not line.strip():
            # Insert a newline for empty lines.
            requests_list.append({
                "insertText": {
                    "location": {"index": current_index},
                    "text": "\n"
                }
            })
            current_index += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            hashes, heading_text = heading_match.groups()
            text_to_insert = heading_text + "\n"
            # Insert heading text.
            requests_list.append({
                "insertText": {
                    "location": {"index": current_index},
                    "text": text_to_insert
                }
            })
            # Apply the appropriate heading style.
            heading_level = min(len(hashes), 6)
            requests_list.append({
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": current_index,
                        "endIndex": current_index + len(text_to_insert)
                    },
                    "paragraphStyle": {"namedStyleType": f"HEADING_{heading_level}"},
                    "fields": "namedStyleType"
                }
            })
            current_index += len(text_to_insert)
        else:
            # Insert normal text followed by a newline.
            text_to_insert = line + "\n"
            requests_list.append({
                "insertText": {
                    "location": {"index": current_index},
                    "text": text_to_insert
                }
            })
            current_index += len(text_to_insert)

    return requests_list


def upload_to_google_docs(final_output, document_title="Weekly PR Dashboard"):
    """
    Creates a new Google Doc and inserts the provided content using structured requests.
    This function uses service account credentials stored in docs_token.json.
    The Markdown content is converted into a set of Google Docs requests for better formatting.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    SCOPES = ['https://www.googleapis.com/auth/documents']
    SERVICE_ACCOUNT_FILE = 'docs_token.json'
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('docs', 'v1', credentials=creds)

    # Create a new document.
    doc_body = {"title": document_title}
    doc = service.documents().create(body=doc_body).execute()
    document_id = doc.get('documentId')
    logger.info(f"Created Google Doc with ID: {document_id}")

    # Convert Markdown to structured Google Docs requests.
    requests_list = convert_markdown_to_requests(final_output)
    if requests_list:
        service.documents().batchUpdate(
            documentId=document_id, body={"requests": requests_list}
        ).execute()
    logger.info("Content uploaded to Google Docs successfully!")

    # Construct the public URL for the document.
    doc_url = f"https://docs.google.com/document/d/{document_id}"
    logger.info(f"Google Doc URL: {doc_url}")

    return document_id


def share_document_with_email(document_id, email, role="writer"):
    """
    Shares the document with the specified email using the Google Drive API.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']
    creds = service_account.Credentials.from_service_account_file("docs_token.json", scopes=DRIVE_SCOPES)
    drive_service = build('drive', 'v3', credentials=creds)

    permission = {
        'type': 'user',
        'role': role,
        'emailAddress': email
    }
    try:
        drive_service.permissions().create(
            fileId=document_id,
            body=permission,
            sendNotificationEmail=False
        ).execute()
        logger.info(f"Shared document {document_id} with {email} as {role}.")
    except Exception as e:
        logger.error(f"Failed to share document: {e}")


def main():
    username = get_authenticated_username()
    logger.info(f"Starting PR dashboard generation for user: {username}")
    last_week_start, last_week_end = get_date_range()
    start_date_str = last_week_start.strftime("%Y-%m-%d")
    end_date_str = last_week_end.strftime("%Y-%m-%d")
    logger.info(f"Using date range: {start_date_str} to {end_date_str}")

    all_prs = fetch_all_prs_by_user(username, start_date_str, end_date_str)
    logger.info(f"Found {len(all_prs)} PRs by {username} in the given period.")

    # Generate the dashboard and summaries (in Markdown format)
    dashboard_md = generate_dashboard(all_prs, start_date_str, end_date_str)
    detailed_summaries_md = generate_detailed_pr_summaries(all_prs)

    overall_concise_summary = (
        "# Overall Concise Summary\n\n"
        "The pull request is part of a larger deployment process aimed at improving security and authentication for publishing site content.\n"
        "The changes made focus on enhancing user experience, improving readability, and ensuring that only authorized users can update content.\n"
        "The pull request has been merged and deployed, and the changes are now live on the test matrix dashboard.\n"
        "Further improvements might include additional testing or new features to enhance functionality.\n"
    )

    weekly_summary_header = (
        "# Weekly PR Summary\n\n"
        f"**Date Range:** {start_date_str} to {end_date_str}\n\n"
        "## Summary by User\n\n"
    )
    user_counts = defaultdict(int)
    for pr in all_prs:
        user = pr.get("user", {}).get("login", "unknown")
        user_counts[user] += 1
    user_table = "| User | PR Count |\n|------|----------|\n"
    for user, count in user_counts.items():
        user_table += f"| {user} | {count} |\n"

    final_output = (
            overall_concise_summary + "\n" +
            weekly_summary_header + user_table + "\n" +
            dashboard_md + "\n" +
            detailed_summaries_md
    )

    document_id = upload_to_google_docs(final_output, document_title="Weekly PR Dashboard")
    logger.info(f"Dashboard and summaries stored in Google Docs with Document ID: {document_id}")

    share_document_with_email(document_id, os.getenv("SHARE_EMAIL"), role="writer")


if __name__ == "__main__":
    main()
