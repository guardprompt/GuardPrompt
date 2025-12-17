import shutil
import uuid
import requests
import img2pdf
from pathlib import Path
from bs4 import BeautifulSoup

from urllib.parse import urlparse, urljoin, unquote, urlunparse
import chardet
import time
import os
import tempfile

import fitz
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from charset_normalizer import from_bytes
import subprocess

from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    PictureDescriptionApiOptions,
    TesseractCliOcrOptions,
)

from docling.document_converter import DocumentConverter, PdfFormatOption


# =========================
# CONFIG
# =========================
UPLOAD_DIR = Path("/tmp/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

LM_STUDIO_ENABLED = os.getenv("LM_STUDIO_ENABLED", "true").lower() == "true"

LM_STUDIO_URL = os.getenv(
    "LM_STUDIO_URL",
    "http://host.docker.internal:1234/v1/chat/completions"
)

LM_MODEL = os.getenv(
    "LM_MODEL",
    "google/gemma-3-4b"
)

print("LM Studio Enabled:", LM_STUDIO_ENABLED)
print("LM Studio URL:", LM_STUDIO_URL)
print("LM Model:", LM_MODEL)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
TEXT_EXTS  = {".txt", ".md", ".csv"}
DOC_EXTS   = {".pdf", ".docx", ".xlsx", ".pptx"}
HTML_EXTS  = {".html", ".htm"}


# =========================
# PROMPTS
# =========================
IMAGE_PROMPT = (
    "Describe the image in English. "
    "Do NOT extract any text and do NOT perform OCR. "
    "Limit to 3 sentences in Markdown.\n\n"
    "Add result after [Picture Description]\n"
)
PDF_IMAGE_PROMPT = IMAGE_PROMPT


# =========================
# MODELS (Swagger)
# =========================
class UrlRequest(BaseModel):
    url: str
    crawl: bool = False
    max_depth: int = 1
    max_pages: int = 10


# =========================
# HELPERS
# =========================

def is_pdf(path: Path) -> bool:
    try:
        return open(path, "rb").read(4) == b"%PDF"
    except:
        return False


def detect_pdf_type(path: Path):
    doc = fitz.open(path)
    has_text, has_images = False, False
    for page in doc:
        if page.get_text().strip():
            has_text = True
        if page.get_images(full=True):
            has_images = True
    if has_text and has_images:
        return "mixed"
    if has_text:
        return "text"
    if has_images:
        return "scanned"
    return "unknown"


def looks_bad(text: str) -> bool:
    if not text or len(text.strip()) < 40:
        return True
    bad = "�□▯▒█"
    return sum(c in bad for c in text) > 2


def safe_decode_html(raw: bytes) -> str:
    """
    Vienintelis leidžiamas dekoderis visai sistemai.
    Jokio r.text, jokio .decode() kitur.
    """
    result = from_bytes(raw).best()
    if result:
        html = str(result)
    else:
        html = raw.decode("utf-8", errors="ignore")

    # papildomas saugiklis nuo "Ã" šiukšlių
    if "Ã" in html and "charset=utf-8" in html.lower():
        try:
            html = raw.decode("windows-1257", errors="ignore")
        except:
            pass

    return html


def clean_html(html: str) -> str:
    # NEBEDAROM jokių encode/decode – html jau švarus Unicode
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript", "iframe", "svg", "img", "footer", "nav", "aside"]):
        tag.decompose()

    text = soup.get_text("\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 3]
    return "\n".join(lines)


def crawl_links_old(start_url: str, max_depth: int = 1, max_pages: int = 10):
    visited = set()
    queue = [(start_url, 0)]

    while queue and len(visited) < max_pages:
        url, depth = queue.pop(0)
        if url in visited or depth > max_depth:
            continue

        visited.add(url)

        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            raw = r.content
            ct = r.headers.get("Content-Type", "")

            html = safe_decode_html(raw)

            yield url, html, ct

            if "html" in ct.lower():
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    new = urljoin(url, a["href"].split("#")[0])
                    if new.startswith("http"):
                        queue.append((new, depth + 1))
                        print(new)

        except Exception as e:
            yield url, None, f"error:{e}"



# ---------- HTML DEKODERIS ----------
def safe_decode_html(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except:
        enc = chardet.detect(raw).get("encoding") or "utf-8"
        return raw.decode(enc, errors="ignore")


# ---------- URL NORMALIZAVIMAS ----------
def normalize_url(url: str) -> str:
    parsed = urlparse(url)

    path = unquote(parsed.path).rstrip("/")

    # pašalinam index failus
    for index in ("index.html", "index.php", "index.htm"):
        if path.endswith("/" + index):
            path = path[: -(len(index) + 1)]

    if not path:
        path = "/"

    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        "", "", ""
    ))


# ---------- PRODUKCINĖ CRAWLER FUNKCIJA ----------
def crawl_links(start_url: str, max_depth: int, max_pages: int):
    visited = set()
    queue = [(normalize_url(start_url), 0)]
    base_domain = urlparse(start_url).netloc.lower()

    session = requests.Session()
    session.headers.update({"User-Agent": "GuardPromptCrawler/1.0"})

    IGNORE_EXT = (".exe", ".zip", ".7z", ".rar", ".mp4", ".avi", ".mov", ".wmv",
                  ".mp3", ".wav", ".flac", ".css", ".js", ".woff", ".woff2",
                  ".jpg", ".png", ".jpeg", ".gif", ".bmp", ".svg", ".ico")
 
    while queue and len(visited) < max_pages:
        url, depth = queue.pop(0)

        url = normalize_url(url)

        if url in visited:
            continue

        if depth > max_depth:
            continue

        if urlparse(url).netloc.lower() != base_domain:
            continue

        if url.lower().endswith(IGNORE_EXT):
            continue

        visited.add(url)

        try:
            r = session.get(url, timeout=15, allow_redirects=True)
            raw = r.content
            ct = r.headers.get("Content-Type", "")

            html = safe_decode_html(raw)

            # ✅ GRĄŽINAM RAW
            yield url, html, raw, ct

            # jei ne HTML, nebeanalizuojam kaip puslapio
            if "html" not in (ct or "").lower():
                continue

            soup = BeautifulSoup(html, "lxml")

            for a in soup.select("a[href]"):
                href = a.get("href")
                if not href:
                    continue

                new = normalize_url(urljoin(url, href))

                if new in visited:
                    continue

                if urlparse(new).netloc.lower() != base_domain:
                    continue

                if new.lower().endswith(IGNORE_EXT):
                    continue

                queue.append((new, depth + 1))

            time.sleep(0.25)

        except Exception as e:
            yield url, None, None, f"error:{e}"



# =========================
# LM STUDIO
# =========================
def lmstudio_options(prompt_text: str):
    return PictureDescriptionApiOptions(
        url=LM_STUDIO_URL,
        params={
            "model": LM_MODEL,
            "max_completion_tokens": 800,
            "temperature": 0.1,
        },
        prompt=prompt_text,
        timeout=600,
    )


# =========================
# PDF CONVERTER
# =========================
def create_pdf_converter(do_ocr: bool, do_picture_description: bool, prompt: str | None):

    enable_picture = do_picture_description and LM_STUDIO_ENABLED

    pipeline = PdfPipelineOptions(
        do_ocr=do_ocr,
        enable_remote_services=LM_STUDIO_ENABLED
    )

    pipeline.accelerator_options = AcceleratorOptions(
        device=AcceleratorDevice.CUDA,
        num_threads=8
    )

    #pipeline.force_backend_text = True
    #pipeline.images_scale = 2.0

    # OCR
    if do_ocr:
        pipeline.ocr_options = TesseractCliOcrOptions(
            lang=["lit"],
            psm=3,
            force_full_page_ocr=True
        )

    pipeline.ocr_batch_size = 16
    pipeline.layout_batch_size = 16
    pipeline.table_batch_size = 16

    #print(vars(pipeline))
    
    
    # ✅ PICTURE DESCRIPTION — TIK JEI LM ĮJUNGTAS
    if enable_picture and prompt:
        pipeline.do_picture_description = True
        pipeline.picture_description_options = lmstudio_options(prompt)
    else:
        pipeline.do_picture_description = False
        # ❗ NIEKO NEPRISKIRIAM – jokių None

    # ✅ Kai LM OFF – išjungiam visus paveikslėlių pipeline
    if not LM_STUDIO_ENABLED:
        pipeline.do_picture_classification = False
        pipeline.do_table_structure = False
        pipeline.do_code_enrichment = False
        pipeline.do_formula_enrichment = False
        pipeline.do_picture_description = False

    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)}
    )

def tesseract_pdf_to_markdown(pdf_path: Path) -> str:
    txt_out = Path(tempfile.NamedTemporaryFile(delete=False).name)

    # ✅ Paleidžiam Tesseract BE OSD, tik tekstą
    subprocess.run([
        "tesseract",
        str(pdf_path),
        str(txt_out),
        "-l", "lit",
        "--psm", "3"
    ], check=True)

    text = Path(str(txt_out) + ".txt").read_text(errors="ignore")

    return to_markdown(text)

def to_markdown(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    md = []
    paragraph = []

    for line in lines:
        # jei eilutė atrodo kaip antraštė (didžiosios raidės)
        if len(line) < 80 and line.isupper():
            if paragraph:
                md.append(" ".join(paragraph))
                paragraph = []
            md.append(f"## {line}")
        else:
            paragraph.append(line)

    if paragraph:
        md.append(" ".join(paragraph))

    return "\n\n".join(md)



def image_caption_fallback_lt(ocr_text: str) -> str:
    payload = {
        "model": LM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": ( IMAGE_PROMPT )
            },
            {
                "role": "user",
                "content": ocr_text[:4000]  # Apsauga nuo per ilgo teksto
            }
        ],
        "temperature": 0.2,
        "max_tokens": 400
    }

    r = requests.post(LM_STUDIO_URL, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]


# =========================
# FASTAPI
# =========================
app = FastAPI()

CONVERTER_CACHE = {}

@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    tmp = UPLOAD_DIR / uuid.uuid4().hex
    tmp.mkdir(parents=True, exist_ok=True)

    path = tmp / file.filename
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    ext = path.suffix.lower()
    do_ocr = False
    do_desc = False
    prompt = None
    use_docling_auto = False

    # IMAGE → PDF
    if ext in IMAGE_EXTS:
        pdf = path.with_suffix(".pdf")
        with open(pdf, "wb") as f:
            f.write(img2pdf.convert(str(path)))
        path = pdf
        do_ocr, do_desc, prompt = True, True, IMAGE_PROMPT

    # PDF
    elif is_pdf(path):
        ptype = detect_pdf_type(path)
        if ptype == "text":
            do_ocr, do_desc = False, False
        else:            
            do_ocr, do_desc, prompt = True, True, PDF_IMAGE_PROMPT
       
    # KITI FAILAI – Docling auto
    elif ext in DOC_EXTS or ext in TEXT_EXTS or ext in HTML_EXTS:
        use_docling_auto = True

    else:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(415, f"Unsupported file type: {ext}")

    if not LM_STUDIO_ENABLED:
        do_desc = False
    
    # def run_once(flag):
    #     if use_docling_auto:
    #         conv = DocumentConverter()
    #     else:
    #         conv = create_pdf_converter(flag, do_desc, prompt)
    #     r = conv.convert(str(path))
    #     return r.document.export_to_markdown()

    def run_once(flag):
        key = (flag, do_desc)
        if key not in CONVERTER_CACHE:
            if use_docling_auto:
                CONVERTER_CACHE[key] = DocumentConverter()
            else:
                CONVERTER_CACHE[key] = create_pdf_converter(flag, do_desc, prompt)

        conv = CONVERTER_CACHE[key]
        r = conv.convert(str(path))
        return r.document.export_to_markdown()


    md = run_once(do_ocr)
    # # ✅ Jei LM Studio OFF – naudojam tiesioginį OCR
    # if not LM_STUDIO_ENABLED and do_ocr:
    #     md = tesseract_pdf_to_markdown(path)
    # else:
    #     md = run_once(do_ocr)


    # Antrą kartą OCR tik jeigu PIRMAS buvo be OCR
    # if not use_docling_auto and not do_ocr and looks_bad(md):
    #     md = run_once(True)

    # ✅ Fallback image captioning (jeigu Docling pats nesugeneravo)
    if ext in IMAGE_EXTS and "[Picture Description]" not in md:
        if LM_STUDIO_ENABLED:        
            try:
                desc = image_caption_fallback_lt(md)
                md += f"\n\n{desc}\n"
            except Exception as e:
                md += f"\n\n[Picture Description]\n(Klaida generuojant aprašymą: {e})\n"


    shutil.rmtree(tmp, ignore_errors=True)
    return {
        "filename": file.filename,
        "markdown": md,
    }

def dispatch_processor(url, content, content_type):

    ct = content_type.lower()

    if "text/html" in ct:
        print("HTML → parser")
        return "html"

    if "application/pdf" in ct or url.lower().endswith(".pdf"):
        print("PDF → Docling")
        return "pdf"

    if any(url.lower().endswith(ext) for ext in [".jpg", ".png", ".jpeg"]):
        print("IMG → OCR")
        return "image"

    print("SKIP:", url)
    return "skip"


@app.post("/convert_url")
async def convert_url(req: UrlRequest):
    results = {}

    pages = crawl_links(req.url, req.max_depth, req.max_pages) if req.crawl else [(req.url, None, None, None)]

    for u, html, raw, ct in pages:
        try:
            if raw is None:
                r = requests.get(u, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                raw = r.content
                ct = r.headers.get("Content-Type", "")
                html = safe_decode_html(raw)

            ct_l = (ct or "").lower()
            ext = Path(urlparse(u).path).suffix.lower()

            is_html = "html" in ct_l
            is_pdf = "pdf" in ct_l or ext == ".pdf"
            is_image = ext in (".jpg", ".jpeg", ".png", ".webp")

            # ---------- HTML ----------
            if is_html:
                cleaned = clean_html(html)

                tmp = UPLOAD_DIR / uuid.uuid4().hex
                tmp.mkdir(parents=True, exist_ok=True)
                fp = tmp / "page.html"
                fp.write_text(html, encoding="utf-8", errors="ignore")

                class DummyUpload:
                    filename = "page.html"
                    file = open(fp, "rb")

                docling_md = (await convert(DummyUpload()))["markdown"]
                shutil.rmtree(tmp, ignore_errors=True)

                results[u] = {
                    "url": u,
                    "markdown": docling_md,
                }
                continue

            # ---------- PDF / IMAGE / DOC ----------
            elif is_pdf or is_image:

                tmp = UPLOAD_DIR / uuid.uuid4().hex
                tmp.mkdir(parents=True, exist_ok=True)
                fname = Path(urlparse(u).path).name or "downloaded"
                fpath = tmp / fname

                fpath.write_bytes(raw) #✅ FIX ČIA

                class DummyUpload:
                    filename = fname
                    file = open(fpath, "rb")

                res = await convert(DummyUpload())

                results[u] = {
                    "url": u,
                    "markdown": res["markdown"],
                }
                
                shutil.rmtree(tmp, ignore_errors=True)
                continue

            # ---------- KITAS TURINYS ----------
            else:
                results[u] = {"skipped": ct}
                continue

        except Exception as e:
            results[u] = {"error": str(e)}

    return results
