import os
import time
import requests
import datetime

import json
import re
from collections import defaultdict
from dotenv import load_dotenv

from MAAS import generate_overall_summary, generate_pr_detailed_summary
from github_api import get_pr_status, get_authenticated_username, fetch_all_prs_by_user
from logger import logger

load_dotenv()



# load all emails as a comma‑separated list
raw = os.getenv("SHARE_EMAILS", "")
SHARE_EMAILS = [e.strip() for e in raw.split(",") if e.strip()]
if not SHARE_EMAILS:
    logger.error("SHARE_EMAILS is not set or empty. Exiting.")
    exit(1)


def get_date_range():
    """Compute date range: 1 day ago to today (for testing)."""
    today = datetime.datetime.now().date()
    last_date = today - datetime.timedelta(days=30)
    logger.info(f"Calculated date range: {last_date} to {today}")
    return last_date, today




def generate_user_summary_bullets(prs):
    """
    Return a list of bullet lines for user summary.
    e.g. ["AdamKaabyia: 5 PRs", "bob: 2 PRs", ...]
    """
    user_counts = defaultdict(int)
    for pr in prs:
        user = pr.get("user", {}).get("login", "unknown")
        user_counts[user] += 1
    bullets = []
    for user, count in user_counts.items():
        bullets.append(f"{user}: {count} PR(s)")
    return bullets


def generate_dashboard_bullets(prs):
    """
    Return a list of bullet lines for the PR dashboard, e.g.:
    [
      "rh-ecosystem-edge/nvidia-ci (#146) - Title: [WIP] Refactor ... - Author: X - Created: ... - Status: open",
      ...
    ]
    """
    bullets = []
    for pr in prs:
        repo_url = pr.get("repository_url", "")
        repo = "/".join(repo_url.split("/")[-2:]) if repo_url else "unknown"
        number = pr.get("number", "N/A")
        title = pr.get("title", "No Title")
        user = pr.get("user", {}).get("login", "unknown")
        created_at = pr.get("created_at", "N/A")
        status = get_pr_status(pr)
        bullets.append(f"{repo} (#{number}) - \"{title}\" - {user} - {created_at} - {status}")
    return bullets


def create_bullet_lines(lines, start_index):
    """
    Insert lines at start_index, then createParagraphBullets on that range.
    Returns (requests, new_end_index).
    """
    requests = []
    current_index = start_index
    text_block = ""
    for line in lines:
        text_block += line + "\n"
    # Insert all lines at once
    insert_req = {
        "insertText": {
            "location": {"index": current_index},
            "text": text_block
        }
    }
    requests.append(insert_req)
    lines_length = len(text_block)

    # Then apply bullets to all those lines at once
    # We'll bullet from current_index to current_index + lines_length - 1
    # But we must ensure we skip the trailing newline.
    bullet_req = {
        "createParagraphBullets": {
            "range": {
                "startIndex": current_index,
                "endIndex": current_index + lines_length - 1
            },
            "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
        }
    }
    requests.append(bullet_req)
    return requests, current_index + lines_length


def generate_detailed_pr_summaries_section(prs, start_index):
    """
    Create requests to insert "Detailed PR Summaries" heading (as a heading style),
    then each PR summary as a sub-heading (HEADING_3), plus normal text.
    Returns (list_of_requests, new_index).
    """
    requests = []
    current_index = start_index

    # Insert a heading for "Detailed PR Summaries"
    heading_text = "Detailed PR Summaries"
    # Insert heading text
    insert_req = {
        "insertText": {
            "location": {"index": current_index},
            "text": heading_text + "\n"
        }
    }
    requests.append(insert_req)
    # Apply heading style
    heading_len = len(heading_text) + 1
    requests.append({
        "updateParagraphStyle": {
            "range": {
                "startIndex": current_index,
                "endIndex": current_index + heading_len
            },
            "paragraphStyle": {"namedStyleType": "HEADING_1"},
            "fields": "namedStyleType"
        }
    })
    current_index += heading_len

    # Insert each PR summary as a subheading
    for pr in prs:
        number = pr.get("number", "N/A")
        title = pr.get("title", "No Title")
        pr_url = pr.get("html_url", "")
        heading_line = f"PR #{number}: {title}"
        if pr_url:
            heading_line += f" (Link: {pr_url})"
        summary_text = generate_pr_detailed_summary(pr)

        # Insert subheading
        insert_heading_req = {
            "insertText": {
                "location": {"index": current_index},
                "text": heading_line + "\n"
            }
        }
        requests.append(insert_heading_req)
        heading_len2 = len(heading_line) + 1
        # Apply subheading style (HEADING_3)
        requests.append({
            "updateParagraphStyle": {
                "range": {
                    "startIndex": current_index,
                    "endIndex": current_index + heading_len2
                },
                "paragraphStyle": {"namedStyleType": "HEADING_3"},
                "fields": "namedStyleType"
            }
        })
        current_index += heading_len2

        # Insert summary text
        text_req = {
            "insertText": {
                "location": {"index": current_index},
                "text": summary_text + "\n\n"
            }
        }
        requests.append(text_req)
        current_index += len(summary_text) + 2

    return requests, current_index


def insert_plain_text_request(text, start_index):
    """
    Returns a tuple (request, length) to insert plain text at a given index.

    Args:
        text (str): The text to insert.
        start_index (int): The position in the document (character index) where the text should be inserted.

    Returns:
        tuple: A tuple containing:
            - The request dictionary formatted for the Google Docs API.
            - The length of the inserted text (including a newline character).
    """
    # Create the request with a newline added at the end.
    req = {"insertText": {"location": {"index": start_index}, "text": text + "\n"}}
    # Calculate the length of the inserted text.
    inserted_length = len(text) + 1  # +1 for the newline character
    return req, inserted_length


def upload_to_google_docs(prs, overall_summary, date_str, user_lines, dashboard_lines, doc_title="Weekly PR Dashboard"):
    """
    Create a new doc with:
      - "Overall Summary" (HEADING_1) + summary text
      - "Weekly PR Summary" (HEADING_1) + date
      - "Summary by User" (HEADING_2) with bullet lines
      - "PR Dashboard" (HEADING_2) with bullet lines
      - "Detailed PR Summaries" section (per PR subheading)

    Returns the doc ID.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    SCOPES = ['https://www.googleapis.com/auth/documents']
    SERVICE_ACCOUNT_FILE = 'docs_token.json'
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    docs_service = build('docs', 'v1', credentials=creds)

    # 1) Create document
    doc_body = {"title": doc_title}
    doc = docs_service.documents().create(body=doc_body).execute()
    doc_id = doc.get("documentId")
    logger.info(f"Created Google Doc with ID: {doc_id}")

    requests_list = []
    current_index = 1

    # 2) Insert "Overall Summary" as heading
    heading_1 = "Overall Summary"
    # insert
    req, text_len = insert_plain_text_request(heading_1, current_index)
    requests_list.append(req)
    # apply heading style
    requests_list.append({
        "updateParagraphStyle": {
            "range": {
                "startIndex": current_index,
                "endIndex": current_index + text_len - 1  # exclude trailing newline
            },
            "paragraphStyle": {"namedStyleType": "HEADING_1"},
            "fields": "namedStyleType"
        }
    })
    current_index += text_len

    # Insert overall summary text
    req, text_len = insert_plain_text_request(overall_summary, current_index)
    requests_list.append(req)
    current_index += text_len

    # 3) Insert "Weekly PR Summary" as heading
    heading_2 = "Weekly PR Summary"
    req, txt_len = insert_plain_text_request(heading_2, current_index)
    requests_list.append(req)
    requests_list.append({
        "updateParagraphStyle": {
            "range": {
                "startIndex": current_index,
                "endIndex": current_index + txt_len - 1
            },
            "paragraphStyle": {"namedStyleType": "HEADING_1"},
            "fields": "namedStyleType"
        }
    })
    current_index += txt_len

    # Insert date range
    date_line = f"Date Range: {date_str}\n"
    req, txt_len = insert_plain_text_request(date_line, current_index)
    requests_list.append(req)
    current_index += txt_len

    # 4) Insert "Summary by User" as heading
    heading_user = "Summary by User"
    req, h_len = insert_plain_text_request(heading_user, current_index)
    requests_list.append(req)
    requests_list.append({
        "updateParagraphStyle": {
            "range": {
                "startIndex": current_index,
                "endIndex": current_index + h_len - 1
            },
            "paragraphStyle": {"namedStyleType": "HEADING_2"},
            "fields": "namedStyleType"
        }
    })
    current_index += h_len

    # Insert bullet lines for user summary
    user_reqs, new_index = create_bullet_lines(user_lines, current_index)
    requests_list.extend(user_reqs)
    current_index = new_index

    # 5) Insert "PR Dashboard" as heading
    heading_dash = "PR Dashboard"
    req, h_len2 = insert_plain_text_request(heading_dash, current_index)
    requests_list.append(req)
    requests_list.append({
        "updateParagraphStyle": {
            "range": {
                "startIndex": current_index,
                "endIndex": current_index + h_len2 - 1
            },
            "paragraphStyle": {"namedStyleType": "HEADING_2"},
            "fields": "namedStyleType"
        }
    })
    current_index += h_len2

    # Insert bullet lines for dashboard
    dash_reqs, new_index = create_bullet_lines(dashboard_lines, current_index)
    requests_list.extend(dash_reqs)
    current_index = new_index

    # 6) Insert Detailed Summaries section
    detail_section_reqs, final_index = generate_detailed_pr_summaries_section(prs, current_index)
    requests_list.extend(detail_section_reqs)
    current_index = final_index

    # 7) Execute the requests in batch
    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests_list}
    ).execute()
    logger.info("All content uploaded with headings & bullet lists.")
    doc_url = f"https://docs.google.com/document/d/{doc_id}"
    logger.info(f"Document URL: {doc_url}")
    return doc_id


def share_document_with_email(document_id, email):
    """Shares the doc with the given email, as 'writer' role, using the Google Drive API."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']
    creds = service_account.Credentials.from_service_account_file("docs_token.json", scopes=DRIVE_SCOPES)
    drive_service = build('drive', 'v3', credentials=creds)

    permission = {"type": "user", "role": "writer", "emailAddress": email}
    drive_service.permissions().create(
        fileId=document_id,
        body=permission,
        sendNotificationEmail=False
    ).execute()
    logger.info(f"Shared doc {document_id} with {email} as writer.")


def main():
    # 1) Get username & date range
    username = get_authenticated_username()
    start_date, end_date = get_date_range()
    date_str = f"{start_date} to {end_date}"

    # 2) Fetch all PRs
    all_prs = fetch_all_prs_by_user(username, start_date, end_date)

    # 3) AI-based overall summary
    overall_summary = generate_overall_summary(all_prs)

    # 4) Build bullet lines for user summary
    user_lines = generate_user_summary_bullets(all_prs)

    # 5) Build bullet lines for PR dashboard
    dashboard_lines = generate_dashboard_bullets(all_prs)

    # 6) Create doc with headings, bullet lines, & detailed summaries
    doc_id = upload_to_google_docs(
        prs=all_prs,
        overall_summary=overall_summary,
        date_str=date_str,
        user_lines=user_lines,
        dashboard_lines=dashboard_lines,
        doc_title="Weekly PR Dashboard"
    )

    # 7) Share doc
    for email in SHARE_EMAILS:
        share_document_with_email(doc_id, email)
        logger.info(f"Shared doc {doc_id} with: {', '.join(SHARE_EMAILS)}")

if __name__ == "__main__":
    main()
