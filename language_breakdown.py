#!/usr/bin/env python3
import os
import requests
from collections import Counter
import matplotlib.pyplot as plt

def get_repos(user, token=None):
    """Retrieve all public repos for the given user (paginated)."""
    url = f"https://api.github.com/users/{user}/repos"
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"
    repos = []
    page = 1
    while True:
        resp = requests.get(url, headers=headers, params={"per_page":100, "page":page})
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def get_language_stats(repos, token=None):
    """Fetch the languages for each repo and sum the bytes per language."""
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"
    lang_counter = Counter()
    for repo in repos:
        resp = requests.get(repo["languages_url"], headers=headers)
        resp.raise_for_status()
        langs = resp.json()
        for lang, count in langs.items():
            lang_counter[lang] += count
    return lang_counter

def plot_pie(stats, user):
    """Generate and save a transparent pie chart with white text."""
    labels = list(stats.keys())
    sizes  = list(stats.values())

    if not labels:
        print("No language data to plot.")
        return

    # Create transparent figure
    plt.figure(figsize=(8, 8), facecolor='none')
    wedges, texts, autotexts = plt.pie(
        sizes,
        labels=labels,
        autopct="%1.1f%%",
        startangle=140,
        textprops={'color': 'white'}
    )

    # Set title with white text
    plt.title(f"Language Breakdown for {user}", color='white')

    # Ensure the plot area is transparent
    ax = plt.gca()
    ax.patch.set_alpha(0)

    plt.axis("equal")  # Equal aspect ratio ensures the pie is circular.
    plt.tight_layout()
    plt.savefig("language_breakdown.png", dpi=300, transparent=True)
    print("→ Saved pie chart as language_breakdown.png (transparent background, white text)")

def main():
    user  = "dwerkjem"
    token = os.getenv("GITHUB_TOKEN")  # optional: set for higher rate limits
    print(f"Fetching repos for '{user}'…")
    repos = get_repos(user, token)
    print(f"Found {len(repos)} repos. Aggregating languages…")
    stats = get_language_stats(repos, token)
    plot_pie(stats, user)

if __name__ == "__main__":
    main()

