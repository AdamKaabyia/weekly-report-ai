# import argparse

def generate_dynamic_prompt(emphasis=None, detail_level=None, focus=None, concise=False):
    """
    Generates a prompt for summarizing GitHub user activities based on provided options.

    Args:
        emphasis (str, optional): The emphasis of the summary (e.g., "impact", "key features"). Defaults to None.
        detail_level (str, optional): The desired level of detail (e.g., "list repositories", "briefly describe"). Defaults to None.
        focus (str, optional): The specific focus of the summary (e.g., "learning and development"). Defaults to None.
        concise (bool, optional): Whether to generate a concise summary. Defaults to False.

    Returns:
        str: The generated prompt text.
    """
    print(emphasis, detail_level, focus, concise)
    prompt_parts = ["Please summarize my GitHub activity, focusing on the code changes I've made, the content of my commit messages, and whether my Pull Requests have been merged (converted).for the past week."]


    if emphasis == "impact":
        prompt_parts.append(" Highlight the impact of my code changes (based on commit messages and PR conversions). Identify the key features or bug fixes I've implemented and the projects where my Pull Requests have been successfully integrated.")
    elif emphasis == "key features":
        prompt_parts.append(" Focus on the key code changes I've introduced and the main points conveyed in my commit messages regarding new features or significant updates.")

    if detail_level == "list repositories":
        prompt_parts.append(" List the repositories I've contributed to. For each, briefly describe significant code changes (based on commit messages), provide a few examples of my commit messages, and indicate which Pull Requests were merged.")
    elif detail_level == "briefly describe":
        prompt_parts.append(" Briefly describe the significant code changes I've made in each repository I contributed to.")

    if focus == "learning and development":
        prompt_parts.append(" Focus on what my code changes and commit messages reveal about my learning and development. What new skills or areas of focus are evident in my contributions? Also, note which Pull Requests were successfully merged, indicating accepted contributions.")

    if concise:
        prompt_parts = ["Briefly summarize my recent GitHub activity based on my code changes, commit messages, and the conversion of my Pull Requests. Provide a high-level overview of my contributions."]

    return " ".join(prompt_parts).strip()
