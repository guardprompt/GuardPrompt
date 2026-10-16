# GuardPrompt sandbox image = Open Terminal + a full office/PDF/data toolset
# baked in at BUILD time. Baking (vs the entrypoint's OPEN_TERMINAL_*_PACKAGES,
# which reinstall on EVERY container start and need egress open each time) means:
#   * built once (docker compose build, run by install.sh/.ps1 on first install)
#   * fast container starts, no re-download
#   * works with a locked-down (block-all) egress firewall at runtime
FROM ghcr.io/open-webui/open-terminal:latest

USER root

# System toolset: LibreOffice (headless docx/pptx/xlsx <-> PDF), pandoc (universal
# doc conversion), fonts, and the native libs WeasyPrint needs (pango/cairo/pixbuf).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer libreoffice-calc libreoffice-impress \
        pandoc \
        poppler-utils \
        fonts-dejavu fonts-liberation fonts-inter fonts-montserrat \
        libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libcairo2 libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Python toolset: office docs, PDF create/read, presentations + charts, data,
# web/parsing, templating, dev ergonomics.
RUN pip install --no-cache-dir --break-system-packages \
        python-docx openpyxl xlsxwriter python-pptx odfpy \
        reportlab fpdf2 pypdf pdfplumber weasyprint \
        pandas numpy tabulate python-dateutil \
        matplotlib plotly kaleido seaborn pillow \
        requests httpx beautifulsoup4 lxml markdown jinja2 pyyaml \
        rich ipython pymupdf cairosvg

# gpdeck: branded presentation helper (professional .pptx + PDF, branded charts,
# AI image generation via the proxy). Baked into /opt/gpdeck and put on PYTHONPATH
# so the agent can `import gpdeck` from anywhere. Only the GENERIC default brand is
# baked; the real per-deployment brand + logo files live in the sandbox volume at
# ~/.gpbrand/ (loaded at runtime), so no customer name/logo enters the image or repo.
COPY assets/gpdeck.py assets/gpweb.py assets/brand.default.json /opt/gpdeck/
COPY assets/ai_label_dark.png assets/ai_label_light.png /opt/gpdeck/
COPY assets/icons/ /opt/gpdeck/icons/
ENV PYTHONPATH=/opt/gpdeck
ENV OT_PROXY_URL=http://open-terminal-proxy:8000

# Inherit the upstream ENTRYPOINT/CMD (egress firewall + open-terminal server).
