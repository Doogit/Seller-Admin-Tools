# Deploy to Azure App Service

Runs Seller-Admin-Tools as a container on **Azure App Service for Containers**,
serving the committed synthetic sample data. The image is built inside Azure, so
**no local Docker is required** — only the Azure CLI.

## One command

```powershell
az login
az account set -s "<your-subscription>"
./deploy/azure-deploy.ps1
```

The script creates a resource group, an Azure Container Registry, builds the
image with `az acr build`, provisions a Linux App Service plan + web app, wires
up managed-identity pull, WebSockets, and the container port, and prints the
URL. First load takes ~30-60s while the container warms.

Override defaults with environment variables before running:

```powershell
$env:LOCATION = "westus2"; $env:APP_NAME = "contoso-seller-admin-tools"
./deploy/azure-deploy.ps1
```

Tear everything down with `az group delete -n rg-seller-admin-tools --yes`.

## What it serves, and the auth boundary

By default the app is **open** and shows **synthetic** sample data (fictional
energy companies, no PII) — appropriate for a demo you can hand someone a link
to. It is *not* appropriate for real pipeline data until you put sign-in in
front of it. The hosted image serves the seeded FastHTML tools (Forecast
Narrative, QBR Assembler, Account Plan); Home/ingest remains a separate local
Streamlit entry.

### Add Entra sign-in (before using real data)

App Service "Easy Auth" gates the whole app behind Microsoft corporate sign-in
with no application code. After the app exists:

```powershell
az webapp auth microsoft update -g rg-seller-admin-tools -n <app-name> `
    --client-id "<entra-app-client-id>" `
    --issuer "https://login.microsoftonline.com/<tenant-id>/v2.0"
az webapp auth update -g rg-seller-admin-tools -n <app-name> `
    --enabled true --action RequireAuthentication --redirect-provider azureactivedirectory
```

Every request then requires a valid corporate login.

## Notes / limitations

- **Untested against a live subscription from this repo checkout.** The seed
  steps baked into the image are verified; the `az` deploy commands assume a
  recent Azure CLI (the `--container-image-name` flag and
  `acrUseManagedIdentityCreds`).
- **State is ephemeral and demo-only.** The SQLite store (`data/agents.db`) is
  baked into the image at build time and its path is hardcoded relative to the
  repo root. Uploads made through the running app persist only until the
  container restarts. For a real multi-user deployment you would mount Azure
  Files for `data/`, or make the DB path env-overridable and point it at durable
  storage — deliberately out of scope for demo mode.
- **Single container, always-on B1 plan.** For a rarely-used demo you can switch
  the plan SKU to `F1` (free, but no Always On → cold starts).
