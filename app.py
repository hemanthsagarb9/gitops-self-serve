import os
import yaml
import base64
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from github import Github, GithubIntegration, Auth

app = FastAPI(title="GitOps PR API")


# --- Config ---
# Option 1: GitHub App (recommended for production)
# GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID")
# GITHUB_PRIVATE_KEY_PATH = os.environ.get("GITHUB_PRIVATE_KEY_PATH")

# Option 2: Fine-grained PAT (simpler for local dev)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")  # e.g. "hemanth/my-gitops-repo"
MANIFEST_PATH = os.environ.get("MANIFEST_PATH", "apps/")  # path prefix in the repo


class ResourceUpdateRequest(BaseModel):
    app_name: str          # e.g. "my-app"
    file_path: str         # e.g. "apps/my-app/deployment.yaml"
    field: str             # e.g. "resources.limits.memory"
    value: str             # e.g. "1Gi"
    auto_merge: bool = True


def get_github_client() -> Github:
    if not GITHUB_TOKEN:
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN not set")
    return Github(GITHUB_TOKEN)


def update_yaml_field(content: str, field: str, value: str) -> str:
    """Navigate a dot-separated field path and update the value in a YAML doc."""
    docs = list(yaml.safe_load_all(content))
    updated = False

    for doc in docs:
        if doc is None:
            continue
        keys = field.split(".")
        obj = doc
        for key in keys[:-1]:
            if isinstance(obj, dict) and key in obj:
                obj = obj[key]
            else:
                obj = None
                break
        if isinstance(obj, dict) and keys[-1] in obj:
            obj[keys[-1]] = value
            updated = True

    if not updated:
        raise HTTPException(status_code=400, detail=f"Field '{field}' not found in YAML")

    # Dump all docs back, preserving multi-doc structure
    return "---\n".join(yaml.dump(doc, default_flow_style=False) for doc in docs)


@app.post("/update")
def update_resource(req: ResourceUpdateRequest):
    gh = get_github_client()
    repo = gh.get_repo(GITHUB_REPO)

    # 1. Read the current file from main
    try:
        file = repo.get_contents(req.file_path, ref="main")
    except Exception:
        raise HTTPException(status_code=404, detail=f"File not found: {req.file_path}")

    original_content = file.decoded_content.decode("utf-8")

    # 2. Update the YAML field
    updated_content = update_yaml_field(original_content, req.field, req.value)

    if original_content == updated_content:
        return {"status": "no_change", "message": "Value is already set"}

    # 3. Create a branch
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    branch_name = f"gitops/{req.app_name}-{timestamp}"
    main_ref = repo.get_git_ref("heads/main")
    repo.create_git_ref(f"refs/heads/{branch_name}", main_ref.object.sha)

    # 4. Commit the change to the new branch
    repo.update_file(
        path=req.file_path,
        message=f"Update {req.field} to {req.value} for {req.app_name}",
        content=updated_content,
        sha=file.sha,
        branch=branch_name,
    )

    # 5. Create a PR
    pr = repo.create_pull(
        title=f"[GitOps] Update {req.app_name}: {req.field} → {req.value}",
        body=(
            f"**Automated change via GitOps API**\n\n"
            f"- **App:** {req.app_name}\n"
            f"- **File:** `{req.file_path}`\n"
            f"- **Field:** `{req.field}`\n"
            f"- **New value:** `{req.value}`\n"
        ),
        head=branch_name,
        base="main",
    )

    # 6. Auto-merge if requested
    merge_status = None
    if req.auto_merge:
        try:
            pr.merge(merge_method="squash")
            merge_status = "merged"
        except Exception as e:
            merge_status = f"merge_failed: {str(e)}"

    return {
        "status": "success",
        "pr_url": pr.html_url,
        "pr_number": pr.number,
        "branch": branch_name,
        "merge_status": merge_status,
    }


@app.get("/health")
def health():
    return {"status": "ok"}
