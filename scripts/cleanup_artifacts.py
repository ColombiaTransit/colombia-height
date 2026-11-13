#!/usr/bin/env python3
"""Delete only allowlisted completed GitHub Actions test artifacts.

Does not touch Releases, workflow logs, caches, or unrelated artifacts.
Default is dry-run. Requires GITHUB_TOKEN with actions:write for deletion.
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone

import requests

PREFIXES = (
    "colombia-dem-inventory",
    "medellin-terrain-rgb-pilot",
    "antioquia-terrain-rgb-pilot",
    "antioquia-terrain-strict",
    "colombia-coast-island-audit-",
    "colombia-dem-extended-islands-inventory",
    "colombia-national-tile-plan-dry-run",
    "colombia-coastal-terrain-pilot",
    "colombia-antioquia-seam-validation",
    "colombia-two-cog-seam-validation",
    "colombia-four-cog-junction-validation",
    "colombia-dem-quality-gates-report",
    "colombia-native-source-seam-audit",
    "colombia-tumaco-native-gap-audit",
    "temporary-dem-source-manifest",
    "colombia-dem-coverage-pilot-shard",
    "colombia-dem-coverage-shard-",
    "colombia-national-dem-coverage-register",
    "temporary-land-source-manifest",
    "colombia-land-coverage-pilot",
    "colombia-land-coverage-shard-",
    "colombia-national-land-coverage-report",
)
API = "https://api.github.com"

def api(session, method, path, **kwargs):
    for attempt in range(3):
        response = session.request(method, API+path, timeout=45, **kwargs)
        if response.status_code in (429,500,502,503,504) and attempt<2:
            time.sleep(2**attempt)
            continue
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub API {response.status_code}: {method} {path}: {response.text[:300]}")
        return response
    raise RuntimeError("Retry exhausted")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--delete", action="store_true", help="Actually delete artifacts (default: preview)")
    parser.add_argument("--minimum-age-hours", type=float, default=0.0)
    parser.add_argument("--keep-latest-per-name", action="store_true")
    args=parser.parse_args()
    if not args.repo or "/" not in args.repo:
        parser.error("Expected --repo OWNER/REPO")
    if args.minimum_age_hours<0:
        parser.error("minimum age cannot be negative")
    token=os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN required")
    s=requests.Session()
    s.headers.update({"Accept":"application/vnd.github+json",
                      "Authorization":f"Bearer {token}",
                      "X-GitHub-Api-Version":"2022-11-28"})
    artifacts=[]
    page=1
    while True:
        resp=api(s,"GET",f"/repos/{args.repo}/actions/artifacts",
                 params={"per_page":100,"page":page}).json()
        page_items=resp.get("artifacts",[])
        artifacts.extend(page_items)
        if len(page_items)<100:
            break
        page+=1
    now=datetime.now(timezone.utc)
    candidates=[]
    for a in artifacts:
        if a.get("expired") or not any(a["name"].startswith(p) for p in PREFIXES):
            continue
        created=datetime.fromisoformat(a["created_at"].replace("Z","+00:00"))
        age=(now-created).total_seconds()/3600
        if age<args.minimum_age_hours:
            continue
        wr=a.get("workflow_run") or {}
        run_id=wr.get("id")
        if not run_id:
            print(f"SKIP {a['id']}: missing workflow run")
            continue
        # Verify completion; never delete artifacts belonging to a running job.
        info=api(s,"GET",f"/repos/{args.repo}/actions/runs/{run_id}").json()
        if info.get("status")!="completed":
            print(f"SKIP {a['id']}: workflow not complete")
            continue
        candidates.append(a)
    if args.keep_latest_per_name:
        newest={}
        for a in artifacts:
            if not any(a["name"].startswith(p) for p in PREFIXES):
                continue
            k=a["name"]
            if k not in newest or a["created_at"]>newest[k]["created_at"]:
                newest[k]=a
        candidates=[a for a in candidates if newest[a["name"]]["id"]!=a["id"]]
    removed=0
    bytes_total=0
    for a in candidates:
        status="DELETE" if args.delete else "WOULD DELETE"
        print(f"{status} artifact={a['id']} name={a['name']} size={a['size_in_bytes']} run={a['workflow_run']['id']}",flush=True)
        if args.delete:
            api(s,"DELETE",f"/repos/{args.repo}/actions/artifacts/{a['id']}")
        removed+=1
        bytes_total+=a["size_in_bytes"]
    print(json.dumps({"mode":"delete" if args.delete else "dry-run",
                      "artifact_count":removed,
                      "bytes":bytes_total,
                      "mebibytes":round(bytes_total/1024**2,2)},indent=2))

if __name__=="__main__":
    main()
