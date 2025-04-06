#!/usr/bin/env python3
import os
import requests
import datetime
import time
from collections import defaultdict
from openai import OpenAI


from dotenv import load_dotenv

from data_gathering import fetch_all_prs_by_user
from generate_summary import process_repo_group

load_dotenv()
# Set up OpenAI API key (must be provided in the environment)
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    print("Error: OPENAI_API_KEY is not set. Exiting.")

client = OpenAI(api_key=openai_api_key)

def get_date_range():
    """
    Computes the start and end dates for last week.
    Since this script is scheduled to run every Monday at midnight UTC,
    last week's period is defined as:
      - Start: Previous Monday (7 days ago)
      - End: Previous Sunday (1 day ago)
    Returns:
        (start_date, end_date) as datetime.date objects.
    """
    today = datetime.datetime.now().date()
    last_week_start = today - datetime.timedelta(days=7)
    last_week_end = today - datetime.timedelta(days=1)
    return last_week_start, last_week_end





def main():
    # Set the GitHub username here
    username = "adamkaabyia"



    # Determine last week's date range
    last_week_start, last_week_end = get_date_range()
    start_date_str = last_week_start.strftime("%Y-%m-%d")
    end_date_str = last_week_end.strftime("%Y-%m-%d")
    print("Start date:", start_date_str, "End date:", end_date_str)

    # Fetch all PRs by the user over the period
    all_prs = fetch_all_prs_by_user(username, start_date_str, end_date_str)
    print(f"Found {len(all_prs)} PRs by {username} in the given period.")

    # Group PRs by repository
    prs_by_repo = defaultdict(list)
    for pr in all_prs:
        repo_url = pr.get("repository_url", "")
        if repo_url:
            # The repository full name is the last two parts of the URL
            repo_parts = repo_url.split("/")[-2:]
            repo_full_name = "/".join(repo_parts)
            prs_by_repo[repo_full_name].append(pr)

    print(f"{len(prs_by_repo)} repositories had PR activity in the last week.")

    # Process each repository group
    for repo_full_name, pr_list in prs_by_repo.items():
        process_repo_group(repo_full_name, pr_list, start_date_str, end_date_str,client)
        time.sleep(3)  # Pause to help avoid rate limits


if __name__ == "__main__":
    main()
