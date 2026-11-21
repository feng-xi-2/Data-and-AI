"""Create (or update) the Jira task + sub-tasks for this work from jira_payload.json (Jira Cloud REST v3).

    $env:JIRA_BASE = "https://<site>.atlassian.net"; $env:JIRA_EMAIL = "<you>"; $env:JIRA_API_TOKEN = "<api token>"
    python jira_create.py ../benchmark/jira_payload.json        # prints the created keys; writes jira_keys.json next to the payload
Same environment variables as the NPI tracker (`tracker.py jira-sync`). Idempotent: an issue whose summary already exists in
the project (open or closed) is updated with a comment instead of duplicated.
"""
import base64
import json
import os
import sys
import urllib.parse
import urllib.request


def call(method, path, body=None):
    base = os.environ["JIRA_BASE"].rstrip("/")
    tok = base64.b64encode(f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()).decode()
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Basic " + tok, "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read().decode()
        return json.loads(t) if t else {}


def adf(text):
    return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": ln}]}
                                                      for ln in text.split("\n") if ln.strip()]}


def find(project, summary):
    jql = f'project = {project} AND summary ~ "\\"{summary[:80]}\\""'
    r = call("GET", "/rest/api/3/search/jql?" + urllib.parse.urlencode({"jql": jql, "fields": "summary", "maxResults": 5}))
    return next((i["key"] for i in r.get("issues", []) if i["fields"]["summary"] == summary), None)


def upsert(project, item, parent=None):
    key = find(project, item["summary"])
    if key:
        call("POST", f"/rest/api/3/issue/{key}/comment", {"body": adf(item["description"])})
        return key
    f = {"project": {"key": project}, "summary": item["summary"], "description": adf(item["description"]),
         "issuetype": {"name": "Subtask" if parent else item.get("type", "Task")}, "labels": item.get("labels", [])}
    if parent:
        f["parent"] = {"key": parent}
    return call("POST", "/rest/api/3/issue", {"fields": f})["key"]


def main(path):
    p = json.load(open(path, encoding="utf-8"))
    keys = {"task": upsert(p["project"], p["task"])}
    for s in p.get("subtasks", []):
        keys[s["summary"]] = upsert(p["project"], {**s, "labels": p["task"].get("labels", [])}, parent=keys["task"])
    for link in p.get("links", []):
        call("POST", f"/rest/api/3/issue/{keys['task']}/remotelink", {"object": {"url": link["url"], "title": link["title"]}})
    json.dump(keys, open(os.path.join(os.path.dirname(path), "jira_keys.json"), "w"), indent=1)
    print(json.dumps(keys, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
