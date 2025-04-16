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
    """Fetches the username of the authenticated user from GitHub."""
    url = "https://api.github.com/user"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {GITHUB_TOKEN}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        username = response.json().get("login")
        if username:
            logger.info(f"Authenticated as: {username}")
            return username
    logger.error("Failed to fetch authenticated user info from GitHub")
    exit(1)


def get_date_range():
    """
    Computes the start and end dates.
    For testing, the start date is set to 1 day ago and the end date to today.
    (Change the timedelta to 7 days for production.)
    Returns a tuple (start_date, end_date) as datetime.date objects.
    """
    today = datetime.datetime.now().date()
    last_week_start = today - datetime.timedelta(days=1)  # TODO: Change to 7 days for production
    last_week_end = today
    logger.info(f"Calculated date range: {last_week_start} to {last_week_end}")
    return last_week_start, last_week_end


def fetch_all_prs_by_user(username, start_date, end_date):
    """Fetches all pull requests created by the given user in the specified date range."""
    headers = {"Accept": "application/vnd.github+json",
               "Authorization": f"token {GITHUB_TOKEN}"}
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
    """Determines the status of a pull request: 'open', 'closed', or 'merged'."""
    pr_number = pr.get("number", "unknown")
    status = pr.get("state", "unknown")
    logger.debug(f"PR #{pr_number}: Initial state is '{status}'.")
    if status == "closed" and "pull_request" in pr:
        pr_url = pr["pull_request"].get("url")
        if pr_url:
            headers = {"Accept": "application/vnd.github+json",
                       "Authorization": f"token {GITHUB_TOKEN}"}
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
                logger.warning(f"Failed to get status for PR #{pr_number}. Returning 'closed'.")
                return "closed"
    logger.debug(f"PR #{pr_number}: Final status is '{status}'.")
    return status


def generate_pr_detailed_summary(pr):
    """Uses the Granite API to generate a detailed summary for a single PR."""
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
    headers_payload = {"Content-Type": "application/json",
                       "Authorization": f"Bearer {granite_token}"}
    response = requests.post(GRANITE_ENDPOINT, headers=headers_payload, json=payload)
    if response.status_code == 200:
        summary = response.json().get("choices", [{}])[0].get("text", "").strip()
        logger.debug(f"Received detailed summary for PR #{pr_number}.")
        return summary
    else:
        logger.error(f"Error calling Granite API for PR #{pr_number}: {response.status_code} {response.text}")
        return ""


def generate_overall_summary(prs):
    """
    Generates an AI-based overall summary of all PRs using the Granite API.
    Aggregates PR titles and statuses, then sends a prompt to summarize.
    """
    pr_list = []
    for pr in prs:
        title = pr.get("title", "No title")
        status = get_pr_status(pr)
        pr_list.append(f"- {title} ({status})")
    pr_summary_text = "\n".join(pr_list)
    prompt = (
            "You are a professional technical writer. Summarize the following list of pull requests into a concise overall summary "
            "that captures the key changes and their impact. Here are the PRs:\n\n" +
            pr_summary_text +
            "\n\nOverall Summary:"
    )
    payload = {
        "model": "granite-8b-code-instruct-128k",
        "prompt": prompt,
        "max_tokens": 150,
        "temperature": 0.7
    }
    granite_token = os.getenv("GRANITE_TOKEN")
    if not granite_token:
        logger.error("GRANITE_TOKEN is not set. Exiting.")
        return "Overall summary unavailable."
    headers_payload = {"Content-Type": "application/json",
                       "Authorization": f"Bearer {granite_token}"}
    response = requests.post(GRANITE_ENDPOINT, headers=headers_payload, json=payload)
    if response.status_code == 200:
        overall = response.json().get("choices", [{}])[0].get("text", "").strip()
        logger.info("Generated overall summary via AI.")
        return overall
    else:
        logger.error(f"Error generating overall summary: {response.status_code} {response.text}")
        return "Overall summary unavailable."


def generate_user_summary_table(prs):
    """
    Builds a 2D list for the 'Summary by User' table.
    """
    header = ["User", "PR Count"]
    rows = [header]
    user_counts = defaultdict(int)
    for pr in prs:
        user = pr.get("user", {}).get("login", "unknown")
        user_counts[user] += 1
    for user, count in user_counts.items():
        rows.append([user, str(count)])
    return rows


def generate_dashboard_table(prs, start_date, end_date):
    """
    Builds a 2D list for the dashboard table.
    """
    header = ["Repo", "PR Number", "Title", "Author", "Created At", "Status"]
    rows = [header]
    for pr in prs:
        repo_url = pr.get("repository_url", "")
        repo = "/".join(repo_url.split("/")[-2:]) if repo_url else "unknown"
        number = pr.get("number", "")
        title = pr.get("title", "")
        user = pr.get("user", {}).get("login", "unknown")
        created_at = pr.get("created_at", "")
        status = get_pr_status(pr)
        rows.append([repo, str(number), title, user, created_at, status])
    return rows


def generate_detailed_pr_summaries(prs):
    """
    Generates detailed summaries for each PR with separate headings.
    Each summary is generated via the Granite API and collected as plain text.
    """
    logger.info("Generating detailed summaries for each PR...")
    summaries = ""
    for pr in prs:
        number = pr.get("number", "unknown")
        title = pr.get("title", "No Title")
        pr_url = pr.get("html_url", "")
        heading = f"PR {number}: {title}"
        if pr_url:
            heading += f" (Link: {pr_url})"
        detailed_summary = generate_pr_detailed_summary(pr)
        summaries += f"{heading}\n\n{detailed_summary}\n\n{'-' * 40}\n\n"
        time.sleep(1)  # Pause to avoid rate limits
    logger.info("Detailed PR summaries generated.")
    return summaries


def build_plain_table_string(table_data):
    """
    Converts table_data (a list of lists) into a plain text table string with columns padded.
    """
    # Determine the maximum width for each column.
    col_widths = []
    for col in zip(*table_data):
        max_width = max(len(str(cell)) for cell in col)
        col_widths.append(max_width)

    lines = []
    # Build header row.
    header = " | ".join(str(cell).ljust(width) for cell, width in zip(table_data[0], col_widths))
    separator = "-+-".join("-" * width for width in col_widths)
    lines.append(header)
    lines.append(separator)

    # Build the rest of the rows.
    for row in table_data[1:]:
        line = " | ".join(str(cell).ljust(width) for cell, width in zip(row, col_widths))
        lines.append(line)

    return "\n".join(lines)


def insert_plain_text_request(text, start_index):
    """
    Returns a tuple (request, length) to insert plain text at a given index.
    """
    req = {"insertText": {"location": {"index": start_index}, "text": text + "\n"}}
    return req, len(text) + 1


def upload_to_google_docs(final_header, user_table_data, dashboard_table_data, detailed_text, overall_summary,
                          document_title="Weekly PR Dashboard"):
    """
    Creates a new Google Doc and inserts content using structured requests:
      - A header section that includes an AI-generated overall summary and a plain header.
      - Two tables (as plain text) for "Summary by User" and the dashboard.
      - Detailed PR summaries as plain text.
    The tables are formatted as plain text tables (using fixed-width formatting) and styled with a monospace font.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    SCOPES = ['https://www.googleapis.com/auth/documents']
    SERVICE_ACCOUNT_FILE = 'docs_token.json'
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('docs', 'v1', credentials=creds)

    # Create the document.
    doc_body = {"title": document_title}
    doc = service.documents().create(body=doc_body).execute()
    document_id = doc.get('documentId')
    logger.info(f"Created Google Doc with ID: {document_id}")

    requests_list = []
    current_index = 1

    # Insert Overall Summary header and overall summary.
    header_text = "Overall Summary\n"
    req, text_len = insert_plain_text_request(header_text, current_index)
    requests_list.append(req)
    current_index += text_len

    req, text_len = insert_plain_text_request(overall_summary, current_index)
    requests_list.append(req)
    current_index += text_len

    # Insert plain header (Weekly PR Summary header).
    req, text_len = insert_plain_text_request(final_header, current_index)
    requests_list.append(req)
    current_index += text_len

    # Build plain text tables.
    user_table_str = build_plain_table_string(user_table_data)
    dashboard_table_str = build_plain_table_string(dashboard_table_data)

    # Insert User Summary Table.
    req, text_len = insert_plain_text_request(user_table_str, current_index)
    requests_list.append(req)
    # Apply monospace font to the table text.
    requests_list.append({
        "updateTextStyle": {
            "range": {"startIndex": current_index, "endIndex": current_index + text_len},
            "textStyle": {"weightedFontFamily": {"fontFamily": "Courier New", "weight": 400}},
            "fields": "weightedFontFamily"
        }
    })
    current_index += text_len

    # Insert a newline.
    req, nl_len = insert_plain_text_request("\n", current_index)
    requests_list.append(req)
    current_index += nl_len

    # Insert Dashboard Table.
    req, text_len = insert_plain_text_request(dashboard_table_str, current_index)
    requests_list.append(req)
    requests_list.append({
        "updateTextStyle": {
            "range": {"startIndex": current_index, "endIndex": current_index + text_len},
            "textStyle": {"weightedFontFamily": {"fontFamily": "Courier New", "weight": 400}},
            "fields": "weightedFontFamily"
        }
    })
    current_index += text_len

    # Insert a newline.
    req, nl_len = insert_plain_text_request("\n", current_index)
    requests_list.append(req)
    current_index += nl_len

    # Insert Detailed PR Summaries.
    req, text_len = insert_plain_text_request(detailed_text, current_index)
    requests_list.append(req)
    current_index += text_len

    # Execute the batch update.
    service.documents().batchUpdate(documentId=document_id, body={"requests": requests_list}).execute()
    logger.info("Content and tables uploaded to Google Docs successfully!")

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

    # Generate an AI-based overall summary of all PRs.
    overall_summary = generate_overall_summary(all_prs)

    # Build plain text header.
    final_plain_header = (
            "Weekly PR Summary\n" +
            f"Date Range: {start_date_str} to {end_date_str}\n\n"
    )

    # Build table data for "Summary by User".
    user_table_data = generate_user_summary_table(all_prs)

    # Build table data for the dashboard.
    dashboard_table_data = generate_dashboard_table(all_prs, start_date_str, end_date_str)

    # Generate detailed PR summaries as plain text.
    detailed_text = generate_detailed_pr_summaries(all_prs)

    # Upload content to Google Docs.
    document_id = upload_to_google_docs(final_plain_header, user_table_data, dashboard_table_data, detailed_text,
                                        overall_summary, document_title="Weekly PR Dashboard")
    logger.info(f"Dashboard and summaries stored in Google Docs with Document ID: {document_id}")

    share_document_with_email(document_id, os.getenv("SHARE_EMAIL"), role="writer")


if __name__ == "__main__":
    main()
