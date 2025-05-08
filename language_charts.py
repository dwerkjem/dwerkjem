#!/usr/bin/env python3
import os
import requests
from collections import Counter
import matplotlib.pyplot as plt

def get_repos(user, token=None):
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
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"
    lang_counter = Counter()
    for repo in repos:
        resp = requests.get(repo["languages_url"], headers=headers)
        resp.raise_for_status()
        for lang, count in resp.json().items():
            lang_counter[lang] += count
    return lang_counter

def plot_pie(stats, user):
    plt.figure(figsize=(6,6), facecolor='none')
    plt.pie(
        stats.values(),
        labels=stats.keys(),
        autopct="%1.1f%%",
        startangle=140,
        textprops={'color': 'white'}
    )
    plt.title(f"Language Breakdown for {user}", color='white')
    ax = plt.gca()
    ax.patch.set_alpha(0)
    plt.axis("equal")
    plt.tight_layout()
    plt.savefig("language_breakdown.png", dpi=300, transparent=True)
    plt.close()

def plot_bar(stats, user):
    languages = list(stats.keys())
    sizes     = list(stats.values())

    plt.figure(figsize=(8,5), facecolor='none')
    bars = plt.bar(languages, sizes)
    plt.xticks(rotation=45, ha='right')
    plt.ylabel("Bytes of Code", color='white')
    plt.title(f"Lines (Bytes) of Code per Language for {user}", color='white')
    ax = plt.gca()
    ax.patch.set_alpha(0)
    # White text for axes
    ax.xaxis.label.set_color('white')
    ax.yaxis.label.set_color('white')
    ax.tick_params(axis='x', colors='white')
    ax.tick_params(axis='y', colors='white')
    plt.tight_layout()
    plt.savefig("language_bar.png", dpi=300, transparent=True)
    plt.close()

def main():
    user  = "dwerkjem"
    token = os.getenv("GITHUB_TOKEN")
    repos = get_repos(user, token)
    stats = get_language_stats(repos, token)
    plot_pie(stats, user)
    plot_bar(stats, user)
    print("→ Saved language_breakdown.png and language_bar.png")

if __name__ == "__main__":
    main()
