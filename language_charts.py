import os
import subprocess
import json
import tempfile
from pathlib import Path
from collections import Counter
from typing import Dict, Iterable, List, Optional

import requests
import matplotlib.pyplot as plt
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

def get_repos(user: str, token: Optional[str] = None, include_private: bool = False) -> List[dict]:
    """Retrieve repos for the given user.

    If include_private and a token is provided, use /user/repos to include private
    repositories owned by the authenticated user. Otherwise, fall back to public
    repos only via /users/{user}/repos.
    """
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"token {token}"

    repos: List[dict] = []
    page = 1

    if include_private and token:
        # Authenticated endpoint includes private repos for the authenticated user
        # Use /user/repos with type=all to get both public and private repos
        url = "https://api.github.com/user/repos"
        params_base = {"per_page": 100, "type": "all"}
    else:
        # Public repos for arbitrary user
        url = f"https://api.github.com/users/{user}/repos"
        params_base = {"per_page": 100}

    while True:
        params = dict(params_base)
        params["page"] = page
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        
        # Debug: log API response details
        if page == 1 and token:
            private_count = sum(1 for repo in data if repo.get("private", False))
            public_count = len(data) - private_count
            print(f"API page 1: {len(data)} repos ({public_count} public, {private_count} private)")
        
        repos.extend(data)
        page += 1
    return repos

def get_language_stats_via_api(repos: Iterable[dict], token: Optional[str] = None) -> Dict[str, Dict[str, int]]:
    """Fetch languages via GitHub API for each repo and sum bytes per language."""
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"token {token}"
    stats: Dict[str, Dict[str, int]] = {}
    
    # Language normalization mapping for GitHub API results
    lang_normalize = {
        "Jupyter Notebook": "Python",  # Jupyter notebooks are primarily Python
        "Batchfile": "Shell",           # Windows batch files
        "PowerShell": "Shell",          # PowerShell scripts
        "Dockerfile": "Docker",         # Docker files
        "YAML": "Configuration",        # YAML config files
        "JSON": "Configuration",        # JSON config files
        "XML": "Configuration",         # XML config files
        "Makefile": "Configuration",    # Build files
        "CMake": "Configuration",       # CMake files
        "Vim script": "Configuration", # Vim scripts
        "Emacs Lisp": "Configuration",  # Emacs config
    }
    
    for repo in repos:
        resp = requests.get(repo["languages_url"], headers=headers)
        resp.raise_for_status()
        for lang, bytes_count in resp.json().items():
            # Normalize language names
            normalized_lang = lang_normalize.get(lang, lang)
            
            if normalized_lang not in stats:
                stats[normalized_lang] = {"bytes": 0, "lines": 0}
            stats[normalized_lang]["bytes"] += bytes_count
            # GitHub API only provides bytes, estimate lines (rough: ~50 chars per line)
            stats[normalized_lang]["lines"] += bytes_count // 50
    return stats

# Minimal extension-to-language mapping for common stacks
EXT_TO_LANG: Dict[str, str] = {
    ".py": "Python",
    ".rs": "Rust",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cxx": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".cs": "C#",
    ".m": "Objective-C",
    ".mm": "Objective-C++",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".md": "Documentation",
    ".txt": "Documentation",
    ".html": "HTML",
    ".css": "CSS",
}

EXCLUDE_DIRS = {".git", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache", "target", "dist", "build"}


def _iter_repo_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            yield Path(dirpath) / fname


def get_language_stats_via_ssh_clone(repos: Iterable[dict]) -> Dict[str, Dict[str, int]]:
    """Clone repos over SSH and compute language sizes by file extension (bytes and lines)."""
    stats: Dict[str, Dict[str, int]] = {}
    
    # Get the authenticated user's details for blame filtering
    user_emails = set()
    try:
        # Get user's email from git config
        result = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            user_emails.add(result.stdout.strip())
    except Exception:
        pass

    def add_file_with_blame(path: Path, repo_path: Path):
        ext = path.suffix.lower()
        lang = EXT_TO_LANG.get(ext)
        if not lang:
            return
        
        # Skip binary files and very large files
        try:
            size = path.stat().st_size
            if size > 1024 * 1024:  # Skip files > 1MB
                return
        except OSError:
            return
        
        # Get blame info for this file
        try:
            rel_path = path.relative_to(repo_path)
            blame_result = subprocess.run(
                ["git", "blame", "--porcelain", str(rel_path)],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            if blame_result.returncode != 0:
                return
                
            # Parse blame output to count lines authored by user
            user_lines = 0
            user_bytes = 0
            current_email = None
            
            for line in blame_result.stdout.splitlines():
                if line.startswith("author-mail "):
                    email = line[12:].strip("<>")
                    current_email = email
                elif line.startswith("\t") and current_email:  # Actual code line
                    # Check if this line was authored by the user
                    if any(email in current_email for email in user_emails) or current_email in user_emails:
                        user_lines += 1
                        user_bytes += len(line)
                        
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            # Fallback: if blame fails, count all lines/bytes
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    user_lines = content.count('\n')
                    user_bytes = len(content.encode('utf-8'))
            except (OSError, UnicodeDecodeError):
                return
        
        if lang not in stats:
            stats[lang] = {"bytes": 0, "lines": 0}
        stats[lang]["bytes"] += user_bytes
        stats[lang]["lines"] += user_lines

    with tempfile.TemporaryDirectory(prefix="langscan_") as tmpdir:
        tmp = Path(tmpdir)
        for repo in repos:
            ssh_url = repo.get("ssh_url") or repo.get("sshUrl")  # be tolerant
            name = repo.get("name") or "repo"
            if not ssh_url:
                continue
            dest = tmp / name
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--depth=1",
                        "--quiet",
                        ssh_url,
                        str(dest),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                # Skip repos we cannot clone (no SSH access or archived)
                continue

            # Walk files and accumulate sizes (only lines authored by user)
            for f in _iter_repo_files(dest):
                add_file_with_blame(f, dest)

    return stats

def plot_pie(stats, user):
    # Use bytes for pie chart proportions
    bytes_data = {lang: data["bytes"] for lang, data in stats.items()}

    # Sort languages by size to make the chart clearer
    items = sorted(bytes_data.items(), key=lambda kv: kv[1], reverse=True)
    langs = [k for k, _ in items]
    values = [v for _, v in items]
    total = sum(values) or 1
    percents = [v / total * 100 for v in values]

    # Define attractive colors for different languages
    language_colors = {
        'Python': '#3776ab',
        'JavaScript': '#f7df1e',
        'TypeScript': '#3178c6',
        'Rust': '#ce422b',
        'C++': '#00599c',
        'C': '#a8b9cc',
        'Java': '#ed8b00',
        'Go': '#00add8',
        'Ruby': '#cc342d',
        'PHP': '#777bb4',
        'Swift': '#fa7343',
        'Kotlin': '#7f52ff',
        'C#': '#239120',
        'Shell': '#89e051',
        'HTML': '#e34c26',
        'CSS': '#1572b6',
        'Objective-C': '#438eff',
        'Docker': '#2496ed',
        'Configuration': '#6c757d',
        'Documentation': '#083fa1',
    }

    # Build color list in the sorted order
    colors = []
    for lang in langs:
        if lang in language_colors:
            colors.append(language_colors[lang])
        else:
            import hashlib
            hash_val = int(hashlib.md5(lang.encode()).hexdigest(), 16)
            colors.append(f'#{hash_val % 0xffffff:06x}')

    # Determine which labels to show on the wedges (reduce overlap)
    min_pct_label = 3.0
    top_n = 6
    top_idx = set(range(min(len(langs), top_n)))
    show_mask = [(percents[i] >= min_pct_label) or (i in top_idx) for i in range(len(langs))]
    labels = [langs[i] if show_mask[i] else '' for i in range(len(langs))]

    def autopct_factory(mask):
        it = iter(mask)
        def _autopct(pct):
            return f"{pct:.1f}%" if next(it) else ''
        return _autopct

    # Slight explode for top slices only
    explodes = [0.06 if i == 0 else (0.03 if i == 1 else 0.0) for i in range(len(langs))]

    plt.figure(figsize=(10, 8), facecolor='none')
    wedges, texts, autotexts = plt.pie(
        values,
        labels=labels,
        autopct=autopct_factory(show_mask),
        startangle=90,
        colors=colors,
        explode=explodes,
        shadow=False,
        textprops={'color': 'white', 'fontsize': 11, 'weight': 'bold'},
        pctdistance=0.7,
        labeldistance=1.15,
        wedgeprops=dict(linewidth=1.5, edgecolor='white')
    )

    # Enhance the percentage text
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontsize(10)
        autotext.set_weight('bold')

    # Enhance the label text
    for text in texts:
        text.set_color('white')
        text.set_fontsize(12)
        text.set_weight('bold')

    # Add legend on the right with all languages and percentages
    legend_labels = [f"{lang}: {pct:.1f}%" for lang, pct in zip(langs, percents)]
    lgd = plt.legend(wedges, legend_labels, loc='center left', bbox_to_anchor=(1.05, 0.5), frameon=False)
    for t in lgd.get_texts():
        t.set_color('white')

    plt.title(f"Language Breakdown by Bytes (Your Code)\n{user}", color='white', fontsize=16, weight='bold', pad=20)

    ax = plt.gca()
    ax.patch.set_alpha(0)
    plt.axis('equal')
    plt.tight_layout()
    plt.savefig('language_breakdown.png', dpi=300, transparent=True, bbox_inches='tight')
    plt.close()

def plot_bar(stats, user):
    langs = list(stats.keys())
    bytes_counts = [stats[lang]["bytes"] for lang in langs]
    lines_counts = [stats[lang]["lines"] for lang in langs]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), facecolor='none')
    
    # Bytes chart
    bars1 = ax1.bar(langs, bytes_counts, color='skyblue', alpha=0.7)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.patch.set_alpha(0)
    ax1.set_facecolor('none')
    ax1.yaxis.grid(True, linestyle='--', alpha=0.5)
    ax1.set_axisbelow(True)
    ax1.set_title(f"Bytes of Code (My Contributions) for {user}", color='white', fontsize=14)
    ax1.set_ylabel("Bytes", color='white', fontsize=12)
    ax1.tick_params(axis='x', rotation=45, labelsize=10, colors='white')
    ax1.tick_params(axis='y', labelsize=10, colors='white')
    
    for bar, val in zip(bars1, bytes_counts):
        ax1.annotate(
            f"{val:,}",
            xy=(bar.get_x() + bar.get_width() / 2, val),
            xytext=(0, 5),
            textcoords="offset points",
            ha='center',
            va='bottom',
            color='white',
            fontsize=9
        )
    
    # Lines chart
    bars2 = ax2.bar(langs, lines_counts, color='lightgreen', alpha=0.7)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.patch.set_alpha(0)
    ax2.set_facecolor('none')
    ax2.yaxis.grid(True, linestyle='--', alpha=0.5)
    ax2.set_axisbelow(True)
    ax2.set_title(f"Lines of Code (My Contributions) for {user}", color='white', fontsize=14)
    ax2.set_ylabel("Lines", color='white', fontsize=12)
    ax2.tick_params(axis='x', rotation=45, labelsize=10, colors='white')
    ax2.tick_params(axis='y', labelsize=10, colors='white')
    
    for bar, val in zip(bars2, lines_counts):
        ax2.annotate(
            f"{val:,}",
            xy=(bar.get_x() + bar.get_width() / 2, val),
            xytext=(0, 5),
            textcoords="offset points",
            ha='center',
            va='bottom',
            color='white',
            fontsize=9
        )

    plt.tight_layout()
    plt.savefig("language_bar.png", dpi=300, transparent=True)
    plt.close()

def main():
    user = "dwerkjem"
    # Load .env if available
    if load_dotenv is not None:
        load_dotenv()
    # Accept common env var names for a GitHub token
    token = (
        os.getenv("GITHUB_TOKEN")
        or os.getenv("GH_TOKEN")
        or os.getenv("GH_PAT")
        or os.getenv("GITHUB_PAT")
    )
    use_git_ssh = os.getenv("USE_GIT_SSH") == "1"

    print(f"Fetching repos for '{user}'…")
    # Prefer API mode if a token is present, even if USE_GIT_SSH=1
    if token and use_git_ssh:
        print("Token detected; forcing API mode over SSH.")
        use_git_ssh = False
    print(f"Auth: {'token detected' if token else 'no token'} | Mode: {'SSH' if use_git_ssh else 'API'}")
    if token:
        try:
            who = requests.get("https://api.github.com/user", headers={"Authorization": f"token {token}"}, timeout=10)
            if who.ok:
                login = who.json().get("login")
                print(f"Authenticated as: {login}")
        except Exception:
            pass

    # Include private repos if we have a token; SSH clone path will include
    # private repos based on your SSH permissions even without token.
    repos = get_repos(user, token, include_private=bool(token))

    # Optional: if USE_GIT_SSH=1 and no token, first try GitHub CLI to list repos; fallback to repos_ssh.txt
    if use_git_ssh and not token:
        # Try GitHub CLI if available and authenticated
        try:
            gh_out = subprocess.run(
                [
                    "gh",
                    "repo",
                    "list",
                    user,
                    "--json",
                    "nameWithOwner,sshUrl,isPrivate,visibility",
                    "-L",
                    "1000",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            gh_data = json.loads(gh_out.stdout)
            repos = [
                {
                    "name": item.get("nameWithOwner", "").split("/")[-1],
                    "full_name": item.get("nameWithOwner"),
                    "ssh_url": item.get("sshUrl"),
                    "private": bool(item.get("isPrivate")),
                }
                for item in gh_data
                if item.get("sshUrl")
            ]
        except Exception:
            # Fallback to manual list file
            pass

    # Fallback: manual list file for SSH mode
    if use_git_ssh and not token:
        list_file = Path("repos_ssh.txt")
        if list_file.exists():
            manual_repos = []
            for line in list_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                manual_repos.append({
                    "name": Path(line).stem.replace(".git", ""),
                    "ssh_url": line,
                    "private": True,
                })
            if manual_repos:
                repos = manual_repos

    # Log the repositories that will be scanned
    def _repo_display_name(r: dict) -> str:
        base = (
            r.get("full_name")
            or r.get("name")
            or r.get("ssh_url")
            or str(r)
        )
        suffix = " (private)" if r.get("private") else ""
        return f"{base}{suffix}"

    repo_names = sorted({_repo_display_name(r) for r in repos})
    priv_count = sum(1 for r in repos if r.get("private"))
    pub_count = len(repos) - priv_count
    print(f"Repos to scan ({len(repo_names)} total | {pub_count} public, {priv_count} private):")
    for nm in repo_names:
        print(f" - {nm}")

    # Compute language stats either via API or SSH clone
    if use_git_ssh:
        print("Computing language stats via git SSH clones (using git blame to count only your contributions)…")
        stats = get_language_stats_via_ssh_clone(repos)
    else:
        print("Computing language stats via GitHub API…")
        print("Note: API mode counts all code in repos, not just your contributions.")
        if not token:
            print("Warning: No GITHUB_TOKEN found; private repos will be excluded in API mode.")
        stats = get_language_stats_via_api(repos, token)

    # If no stats gathered, bail out gracefully
    if not stats:
        print("No language data found. Check credentials or repository list.")
        return

    plot_pie(stats, user)
    plot_bar(stats, user)
    print("Saved language_breakdown.png and language_bar.png")

if __name__ == "__main__":
    main()

