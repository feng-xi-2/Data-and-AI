"""Open (or update) the GitHub issue and pull request for this work in the user's repository.

    python github_publish.py --repo <owner>/<repo> --branch <branch> --issue-body <md> --pr-body <md> [--title "..."]
Token: GITHUB_TOKEN, else Git Credential Manager (`git credential fill`, the same login git push uses). Never printed.
"""
import argparse
import json
import os
import subprocess
import urllib.error
import urllib.request


def token():
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True, timeout=30).stdout
    return next((ln.split("=", 1)[1] for ln in out.splitlines() if ln.startswith("password=")), None)


def gh(method, path, body=None):
    req = urllib.request.Request("https://api.github.com" + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": "token " + token(), "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"GitHub {method} {path}: {e.code} {e.read().decode()[:300]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", default="main")
    ap.add_argument("--title", default="RTCIS / PrIME 2014 / PrIME 2022 knowledge graph (validated, Cosmos Gremlin, benchmark)")
    ap.add_argument("--issue-body", required=True)
    ap.add_argument("--pr-body", required=True)
    a = ap.parse_args()
    ib, pb = open(a.issue_body, encoding="utf-8").read(), open(a.pr_body, encoding="utf-8").read()
    owner = a.repo.split("/")[0]
    issues = gh("GET", f"/repos/{a.repo}/issues?state=all&per_page=100")
    issue = next((i for i in issues if i["title"] == a.title and "pull_request" not in i), None)
    issue = gh("PATCH", f"/repos/{a.repo}/issues/{issue['number']}", {"body": ib}) if issue else \
        gh("POST", f"/repos/{a.repo}/issues", {"title": a.title, "body": ib})
    pb = pb.replace("{ISSUE}", f"#{issue['number']}")
    prs = gh("GET", f"/repos/{a.repo}/pulls?state=open&head={owner}:{a.branch}")
    pr = gh("PATCH", f"/repos/{a.repo}/pulls/{prs[0]['number']}", {"body": pb, "title": a.title}) if prs else \
        gh("POST", f"/repos/{a.repo}/pulls", {"title": a.title, "head": a.branch, "base": a.base, "body": pb})
    print(json.dumps({"issue": issue["html_url"], "pr": pr["html_url"]}))


if __name__ == "__main__":
    main()
