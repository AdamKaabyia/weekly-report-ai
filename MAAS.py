import os
import time
import requests
import datetime

import json
import re
from collections import defaultdict
from dotenv import load_dotenv
from logger import logger
from github_api import get_pr_status
load_dotenv()


# Granite API endpoint
GRANITE_ENDPOINT = os.getenv("GRANITE_ENDPOINT")
if not GRANITE_ENDPOINT:
    logger.error("GRANITE_ENDPOINT is not set. Exiting.")
    exit(1)





def generate_pr_detailed_summary(pr):
    """Generate a detailed summary for a single PR via Granite."""
    title = pr.get("title", "No title")
    body = pr.get("body", "No description.")
    prompt = (
        "You are a knowledgeable code and workflow analyst. Summarize this PR in detail, "
        "highlighting purpose, changes, insights, and any actionable observations.\n\n"
        f"Title: {title}\n\nBody: {body}\n\nDetailed Summary:"
    )
    granite_token = os.getenv("GRANITE_TOKEN")
    if not granite_token:
        logger.error("GRANITE_TOKEN not set.")
        return ""
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {granite_token}"}
    payload = {
        "model": "granite-8b-code-instruct-128k",
        "prompt": prompt,
        "max_tokens": 200,
        "temperature": 0.7
    }
    resp = requests.post(GRANITE_ENDPOINT, headers=headers, json=payload)
    if resp.status_code == 200:
        return resp.json().get("choices", [{}])[0].get("text", "").strip()
    else:
        logger.error(f"Granite error: {resp.status_code} {resp.text}")
        return ""



def generate_overall_summary(prs):
    """
    AI-based overall summary from PR titles/statuses.
    """
    lines = []
    for pr in prs:
        title = pr.get("title", "No title")
        status = get_pr_status(pr)
        lines.append(f"- {title} ({status})")
    pr_summary = "\n".join(lines)
    prompt = (
        "You are a professional technical writer. Summarize these PRs into a concise overview:\n\n"
        f"{pr_summary}\n\nOverall Summary:"
    )
    granite_token = os.getenv("GRANITE_TOKEN")
    if not granite_token:
        logger.error("GRANITE_TOKEN not set.")
        return "Overall summary unavailable."

    payload = {
        "model": "granite-8b-code-instruct-128k",
        "prompt": prompt,
        "max_tokens": 150,
        "temperature": 0.7
    }
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {granite_token}"}
    resp = requests.post(GRANITE_ENDPOINT, headers=headers, json=payload)
    if resp.status_code == 200:
        text = resp.json().get("choices", [{}])[0].get("text", "").strip()
        logger.info("Generated overall summary via AI.")
        return text
    else:
        logger.error(f"Granite overall summary error: {resp.status_code} {resp.text}")
        return "Overall summary unavailable."
