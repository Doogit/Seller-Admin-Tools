# Seller-Admin-Tools (FastHTML tools 1-3) as a self-contained image for Azure App Service.
# Demo mode: the committed sample pipeline + account facts are seeded at BUILD
# time so the container serves realistic data on first request with no runtime
# seeding and no external data source.
FROM python:3.12-slim

WORKDIR /app

# Deps are pinned (FastHTML, pandas, python-pptx) and ship manylinux wheels —
# no build toolchain required.
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bake the demo database. seed_snapshots.py loads two weekly pipeline snapshots
# (Forecast Narrative + QBR Assembler); seed_account_facts.py adds the account
# facts the Account Plan page uses — so all three tools are populated. The store
# hardcodes data/agents.db relative to the repo root (=/app), so no path env var
# is needed. (tests/test_packaging.py asserts both seeds land.)
RUN python sample_data/seed_snapshots.py \
 && python deploy/seed_account_facts.py

# App Service routes to the port named by the WEBSITES_PORT app setting; keep it
# in sync with the port uvicorn binds (see deploy/azure-deploy.ps1).
ENV PORT=8000
ENV SELLER_ADMIN_TOOLS_ALLOW_REMOTE=1
EXPOSE 8000

# Bind 0.0.0.0 so App Service can reach the container. Remote host access is
# opt-in through SELLER_ADMIN_TOOLS_ALLOW_REMOTE above; mutating requests still
# require same-origin Origin/Referer in web.security.
CMD ["sh", "-c", "uvicorn web.server:app --host 0.0.0.0 --port ${PORT}"]
