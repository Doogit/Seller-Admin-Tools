# Seller-Admin-Tools (Streamlit) as a self-contained image for Azure App Service.
# Demo mode: the committed sample pipeline + account facts are seeded at BUILD
# time so the container serves realistic data on first request with no runtime
# seeding and no external data source.
FROM python:3.12-slim

WORKDIR /app

# Deps are pinned (streamlit, pandas, python-pptx) and ship manylinux wheels —
# no build toolchain required.
COPY requirements.txt .
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
# in sync with the port Streamlit binds (see deploy/azure-deploy.ps1).
ENV PORT=8000
EXPOSE 8000

# Streamlit defaults to loopback; bind 0.0.0.0 so App Service can reach it. Easy
# Auth, when enabled, fronts the app, so this is not exposed to the open net.
CMD ["sh", "-c", "streamlit run app/Home.py --server.address=0.0.0.0 --server.port=${PORT} --server.headless=true --browser.gatherUsageStats=false"]
