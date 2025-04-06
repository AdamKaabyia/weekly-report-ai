
from collections import defaultdict



def generate_markdown(prs, start_date, end_date):
    """
    Generates a Markdown-formatted summary report of pull requests.

    Args:
        prs (list): List of PR items.
        start_date (str): Start date of the period.
        end_date (str): End date of the period.

    Returns:
        A string containing the Markdown report.
    """
    md = f"# Weekly PR Summary\n\n"
    md += f"**Date Range:** {start_date} to {end_date}\n\n"
    if not prs:
        md += "No pull requests were created in this period.\n"
        return md

    # Summary table by user
    user_counts = defaultdict(int)
    for pr in prs:
        user = pr.get("user", {}).get("login", "unknown")
        user_counts[user] += 1

    md += "## Summary by User\n\n"
    md += "| User | PR Count |\n"
    md += "|------|----------|\n"
    for user, count in user_counts.items():
        md += f"| {user} | {count} |\n"

    md += "\n## Pull Request Details\n\n"
    md += "| Repo | PR Number | Title | Author | Created At | URL |\n"
    md += "|------|-----------|-------|--------|------------|-----|\n"
    for pr in prs:
        # Extract repo name from repository_url
        repo_url = pr.get("repository_url", "")
        repo = "/".join(repo_url.split("/")[-2:]) if repo_url else "unknown"
        number = pr.get("number", "")
        title = pr.get("title", "").replace("|", "\\|")
        user = pr.get("user", {}).get("login", "unknown")
        created_at = pr.get("created_at", "")
        html_url = pr.get("html_url", "")
        md += f"| {repo} | {number} | {title} | {user} | {created_at} | [Link]({html_url}) |\n"
    return md


def generate_openai_summary(report_md,client):
    """
    Uses OpenAI's Chat Completion API to generate a concise summary of the weekly PR report.

    Args:
        report_md (str): The detailed Markdown PR report.

    Returns:
        A string containing the concise summary.
    """
    prompt = (
        "Generate a concise summary of the following weekly PR report. "
        "Focus on the key insights and overall activity trends:\n\n"
        f"{report_md}\n\nSummary:"
    )
    response = client.chat.completions.create(model="gpt-3.5-turbo",  # or "gpt-4" if preferred
    messages=[
        {"role": "system", "content": "You are a helpful assistant that summarizes weekly PR reports."},
        {"role": "user", "content": prompt}
    ],
    max_tokens=150,
    temperature=0.7)
    summary = response.choices[0].message.content.strip()
    return summary

def process_repo_group(repo_full_name, pr_list, start_date_str, end_date_str,client):
    """
    Processes a single repository group (PRs from one repository) by generating a detailed Markdown
    report, obtaining an OpenAI-generated concise summary, and writing the results to a README file.

    Args:
        repo_full_name (str): Repository full name (e.g., "owner/repo").
        pr_list (list): List of PR items for this repository.
        start_date_str (str): Start date (YYYY-MM-DD).
        end_date_str (str): End date (YYYY-MM-DD).
    """
    print(f"\nProcessing repository: {repo_full_name}")
    if not pr_list:
        print(f"No PR activity in {repo_full_name} for the period. Skipping.")
        return

    detailed_report = generate_markdown(pr_list, start_date_str, end_date_str)
    print("Generating concise summary using OpenAI...")
    concise_summary = generate_openai_summary(detailed_report,client)

    content = f"# Weekly PR Summary for {repo_full_name}\n\n"
    content += f"## Concise Summary\n\n{concise_summary}\n\n"
    content += "---\n\n"
    content += detailed_report

    repo_name = repo_full_name.split("/")[-1]
    filename = f"README_{repo_name}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Summary stored in {filename}")
