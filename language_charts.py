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
    repos, page = [], 1
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
    counter = Counter()
    for repo in repos:
        resp = requests.get(repo["languages_url"], headers=headers)
        resp.raise_for_status()
        for lang, count in resp.json().items():
            counter[lang] += count
    return counter

def plot_pie(stats, user):
    plt.figure(figsize=(6,6), facecolor='none')
    plt.pie(
        stats.values(),
        labels=stats.keys(),
        autopct="%1.1f%%",
        startangle=140,
        textprops={'color': 'white', 'fontsize': 10}
    )
    plt.title(f"Language Breakdown for {user}", color='white', fontsize=14)
    ax = plt.gca()
    ax.patch.set_alpha(0)
    plt.axis("equal")
    plt.tight_layout()
    plt.savefig("language_breakdown.png", dpi=300, transparent=True)
    plt.close()

def plot_bar(stats, user):
    langs  = list(stats.keys())
    counts = list(stats.values())

    fig, ax = plt.subplots(figsize=(10, 6), facecolor='none')
    bars = ax.bar(langs, counts)

    # Clean up spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.patch.set_alpha(0)
    ax.set_facecolor('none')

    # Gridlines
    ax.yaxis.grid(True, linestyle='--', alpha=0.5)
    ax.set_axisbelow(True)

    # Titles & labels
    ax.set_title(f"Lines of Code for {user}", color='white', fontsize=16)
    ax.set_ylabel("Bytes of Code", color='white', fontsize=12)

    # Rotate & style ticks
    ax.tick_params(axis='x', rotation=45, labelsize=10, colors='white')
    ax.tick_params(axis='y', labelsize=10, colors='white')

    # Annotate each bar with the total count only
    for bar, val in zip(bars, counts):
        ax.annotate(
            f"{val:,}",
            xy=(bar.get_x() + bar.get_width() / 2, val),
            xytext=(0, 5),
            textcoords="offset points",
            ha='center',
            va='bottom',
            color='white',
            fontsize=10
        )

    plt.tight_layout()
    plt.savefig("language_bar.png", dpi=300, transparent=True)
    plt.close()

def main():
    user  = "dwerkjem"
    token = os.getenv("GITHUB_TOKEN")
    print(f"Fetching repos for '{user}'…")
    repos = get_repos(user, token)
    stats = get_language_stats(repos, token)

    plot_pie(stats, user)
    plot_bar(stats, user)
    print("→ Saved language_breakdown.png and language_bar.png")

if __name__ == "__main__":
    main()

