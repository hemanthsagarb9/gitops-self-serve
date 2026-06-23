# GitOps Self-Serve API

A FastAPI service that lets you update Kubernetes resource configurations via API calls. It modifies manifests in a GitOps repo, creates a PR, and auto-merges it — so ArgoCD picks up the change and syncs it to your cluster.

## Architecture

```
┌──────────┐       ┌──────────────┐       ┌────────┐       ┌──────────┐
│  You /   │ POST  │  GitOps API  │  PR   │ GitHub │ sync  │  ArgoCD  │
│  Client  │──────▶│  (FastAPI)   │──────▶│  Repo  │──────▶│ minikube │
└──────────┘       └──────────────┘       └────────┘       └──────────┘
```

**Example:** Change `sample-app` memory limit from 512Mi to 1Gi:

```bash
curl -X POST http://<api-url>/update \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "sample-app",
    "file_path": "manifests/sample-app/deployment.yaml",
    "field": "spec.template.spec.containers.0.resources.limits.memory",
    "value": "1Gi"
  }'
```

The API will:
1. Read the current manifest from GitHub
2. Create a new branch
3. Update the YAML field
4. Open a PR
5. Auto-merge the PR
6. ArgoCD detects the change and syncs the new config to minikube

## Repo Structure

```
gitops-self-serve/
├── app.py                              # FastAPI application
├── Dockerfile                          # Container image for the API
├── requirements.txt                    # Python dependencies
├── k8s/
│   └── deployment.yaml                 # Deploys the API into minikube
└── manifests/
    ├── argocd-application.yaml         # ArgoCD Application (points to sample-app)
    └── sample-app/
        └── deployment.yaml             # Target app managed by ArgoCD
```

## Setup

### 1. Prerequisites

- minikube running
- ArgoCD installed in minikube
- GitHub Fine-grained PAT with `Contents: Read/Write` and `Pull requests: Read/Write`

### 2. Install ArgoCD (if not already)

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### 3. Register the sample-app with ArgoCD

```bash
kubectl apply -f manifests/argocd-application.yaml
```

### 4. Deploy the API to minikube

```bash
# Build inside minikube's docker
eval $(minikube docker-env)
docker build -t gitops-api:latest .

# Create secrets
kubectl create secret generic gitops-api-secrets \
  --from-literal=github-token=ghp_YOUR_TOKEN \
  --from-literal=github-repo=hemanthsagarb9/gitops-self-serve

# Deploy
kubectl apply -f k8s/deployment.yaml

# Get the API URL
minikube service gitops-api --url
```

### 5. Test it

```bash
# Check health
curl http://<api-url>/health

# Update sample-app memory limit from 512Mi to 1Gi
curl -X POST http://<api-url>/update \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "sample-app",
    "file_path": "manifests/sample-app/deployment.yaml",
    "field": "spec.template.spec.containers.0.resources.limits.memory",
    "value": "1Gi"
  }'
```

## GitHub Authentication

| Option | Setup | Best For |
|--------|-------|----------|
| **Fine-grained PAT** | GitHub Settings > Developer Settings > Personal access tokens | Local dev / prototyping |
| **GitHub App** | Create App, install on repo, use private key for tokens | Production / org-level |

Set `GITHUB_TOKEN` and `GITHUB_REPO` as environment variables (or via K8s secret as shown above).
