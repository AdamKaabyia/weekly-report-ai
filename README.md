# Weekly PR Dashboard Generator

This project is a Python-based tool that automates the creation of a weekly pull request (PR) dashboard. It gathers PR data for a specified GitHub user within a calculated date range (last week, defined as the previous Monday to Sunday), generates a Markdown dashboard of the PR information, and produces detailed summaries for each PR using the Granite-8B-Code-Instruct-128k API.

## Overview

The script performs the following functions:
- **Date Range Calculation:** Automatically computes last week’s start (previous Monday) and end (previous Sunday) dates.
- **GitHub API Integration:** Fetches all pull requests created by a user within the specified date range.
- **PR Status Determination:** Checks each PR to determine if it is open, closed, or merged.
- **Granite API Summaries:** Uses the Granite API to generate detailed summaries for each PR.
- **Markdown Report Generation:** Produces a Markdown-formatted dashboard including:
  - An overall concise summary
  - A weekly summary table by user
  - A detailed PR dashboard with repository, PR number (link), title, author, creation date, and status
  - Detailed summaries of each pull request

## Requirements

- **Python Version:** Python 3.7 or later.
- **Libraries and Dependencies:**
  - [requests](https://pypi.org/project/requests/)
  - [python-dotenv](https://pypi.org/project/python-dotenv/)
  - Standard libraries: `os`, `time`, `datetime`, `logging`, `collections`
- A valid GitHub token for making authenticated API calls.
- A configured Granite API endpoint and token for generating detailed summaries.

## Setup

### 1. Clone the Repository

Clone the project repository and navigate into the directory:

```bash
git clone https://github.com/AdamKaabyia/weekly-report-ai
cd weekly-report-ai
```

### 2. Create a Virtual Environment (Recommended)

Create and activate a virtual environment to manage dependencies:

```bash
# On Unix or macOS
python3 -m venv venv
source venv/bin/activate

# On Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root directory and add the following entries:

```dotenv
GRANITE_ENDPOINT=<your_granite_api_endpoint>
GITHUB_TOKEN=<your_github_token>
GRANITE_TOKEN=<your_granite_api_token>
```

Make sure you replace the placeholder values with your actual API endpoints and tokens.

## Usage

After setting up the environment variables, run the script with:

```bash
python main.py
```

This will generate a `dashboard.md` file in the current directory that contains the complete PR dashboard and detailed summaries.

## Automation and Manual Trigger

The dashboard generation process is automated through a GitHub workflow that triggers automatically every **7 days**. Additionally, you have the option to manually trigger the workflow if needed to update the dashboard on demand.

## How to Setup MASS

For those looking to integrate with MASS (Model as a Service) or set up similar workflows, please refer to the following guide:

[MASS Setup Guide](https://maas.apps.prod.rhoai.rh-aiservices-bu.com/)
