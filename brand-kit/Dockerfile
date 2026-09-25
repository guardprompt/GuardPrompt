# brand-kit-sync: mirrors a SharePoint document library (official visual-identity
# assets) into the sandbox brand volume. Stdlib only — no third-party deps.
FROM python:3.12-slim
WORKDIR /app
# Copy the whole context so sync.py and its runtime package are included together
# (.dockerignore keeps junk out of the context).
COPY . /app/
# Runs as root to write into the shared sandbox volume (/home/user, root-owned).
CMD ["python", "/app/sync.py"]
