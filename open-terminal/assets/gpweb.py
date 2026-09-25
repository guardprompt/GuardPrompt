"""
gpweb - designer-grade PDF decks from HTML/CSS via WeasyPrint.

Use this when the user wants a VISUALLY STRIKING **PDF** (gradients, custom
typography, full-bleed imagery) and does NOT need to edit it in PowerPoint.
For editable .pptx use gpdeck instead.

    import gpweb
    w = gpweb.Web("pristatymas")
    w.cover("Pavadinimas", "Paantraštė")
    w.bullets("Ką darome", ["Punktas", "Punktas", "Punktas"])
    w.image("Nuotrauka", "/home/user/.gpbrand/kit/foto.jpg", "Aprašymas")
    w.quote("Įkvepianti mintis.", "Autorius")
    w.closing("Ačiū!", "www.pavyzdys.lt")
    w.save()          # -> pristatymas.pdf

Brand (colours/fonts/logo) is shared with gpdeck via brand.json.
"""

import base64
import html
import os

from gpdeck import _load_brand  # reuse the same brand resolution


def _b64(path):
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        ext = path.rsplit(".", 1)[-1].lower()
        mime = {"jpg": "jpeg", "svg": "svg+xml"}.get(ext, ext)
        return f"data:image/{mime};base64,{data}"
    except Exception:
        return ""


def _e(s):
    return html.escape(str(s))


class Web:
    def __init__(self, name="presentation", brand=None, theme=None):
        """theme: one of gpdeck.THEMES (corporate/dark/bold/minimal/emerald)."""
        self.name = name[:-4] if name.lower().endswith(".pdf") else name
        self.b = _load_brand(brand, theme=theme)
        self.slides = []

    # ---- slides ----------------------------------------------------------

    def cover(self, title, subtitle=""):
        logo = self.b.get("logo_white") or self.b.get("logo")
        logo_html = (f'<img class="logo" src="{_b64(logo)}">'
                     if logo and os.path.exists(logo) else
                     f'<div class="logo-text">{_e(self.b["company"])}</div>')
        self.slides.append(f'''
        <section class="slide cover">
          {logo_html}
          <div class="cover-body">
            <div class="accent-bar"></div>
            <h1>{_e(title)}</h1>
            <p class="sub">{_e(subtitle)}</p>
          </div>
        </section>''')
        return self

    def section(self, title, number=""):
        num = f'<div class="secnum">{_e(number)}</div>' if number else ""
        self.slides.append(f'''
        <section class="slide section">
          {num}<h2>{_e(title)}</h2>
        </section>''')
        return self

    def bullets(self, title, items):
        lis = "".join(f"<li>{_e(it)}</li>" for it in items)
        self.slides.append(f'''
        <section class="slide content">
          <div class="head"><h3>{_e(title)}</h3><div class="rule"></div></div>
          <ul>{lis}</ul>
          {self._footer()}
        </section>''')
        return self

    def columns(self, title, left_title, left_items, right_title, right_items):
        def col(ct, items):
            lis = "".join(f"<li>{_e(it)}</li>" for it in items)
            return (f'<div class="col"><div class="col-h">{_e(ct)}</div>'
                    f'<ul>{lis}</ul></div>')
        self.slides.append(f'''
        <section class="slide content">
          <div class="head"><h3>{_e(title)}</h3><div class="rule"></div></div>
          <div class="cols">{col(left_title, left_items)}
            {col(right_title, right_items)}</div>
          {self._footer()}
        </section>''')
        return self

    def image(self, title, image_path, caption=""):
        src = _b64(image_path) if image_path and os.path.exists(image_path) else ""
        cap = f'<p class="cap">{_e(caption)}</p>' if caption else ""
        self.slides.append(f'''
        <section class="slide content">
          <div class="head"><h3>{_e(title)}</h3><div class="rule"></div></div>
          <div class="imgwrap"><img src="{src}"></div>{cap}
          {self._footer()}
        </section>''')
        return self

    def image_full(self, image_path, title="", subtitle=""):
        src = _b64(image_path) if image_path and os.path.exists(image_path) else ""
        cap = ""
        if title:
            cap = (f'<div class="fcap"><h3>{_e(title)}</h3>'
                   f'<p>{_e(subtitle)}</p></div>')
        self.slides.append(f'''
        <section class="slide imgfull" style="background-image:url({src})">
          {cap}
        </section>''')
        return self

    def quote(self, text, author=""):
        au = f'<div class="qa">— {_e(author)}</div>' if author else ""
        self.slides.append(f'''
        <section class="slide quote">
          <div class="qmark">&ldquo;</div>
          <blockquote>{_e(text)}</blockquote>{au}
        </section>''')
        return self

    def closing(self, title="Ačiū!", subtitle=""):
        logo = self.b.get("logo_white") or self.b.get("logo")
        logo_html = (f'<img class="logo" src="{_b64(logo)}">'
                     if logo and os.path.exists(logo) else "")
        self.slides.append(f'''
        <section class="slide cover closing">
          <div class="cover-body">
            <div class="accent-bar"></div>
            <h1>{_e(title)}</h1><p class="sub">{_e(subtitle)}</p>
          </div>{logo_html}
        </section>''')
        return self

    def gen_image(self, prompt, filename=None):
        """Convenience: generate an AI image (delegates to gpdeck)."""
        import gpdeck
        return gpdeck.gen_image(prompt, filename)

    # ---- internals -------------------------------------------------------

    def _footer(self):
        return f'<div class="foot">{_e(self.b["company"])}</div>'

    def _css(self):
        b = self.b
        import gpdeck
        lbl_dark = _b64(gpdeck.AI_LABEL_DARK)    # black label, for light slides
        lbl_light = _b64(gpdeck.AI_LABEL_LIGHT)  # white label, for dark slides
        default_lbl = lbl_light if gpdeck._is_dark(b["bg"]) else lbl_dark
        ai = f'''
        .slide::after {{ content:""; position:absolute; top:.3in; right:.35in;
            width:.7in; height:.22in; background:url({default_lbl}) right/contain
            no-repeat; opacity:.85; z-index:9; }}
        .cover::after, .imgfull::after {{ background-image:url({lbl_light}); }}
        ''' if lbl_dark else ""
        return ai + f'''
        @page {{ size: 13.333in 7.5in; margin: 0; }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: "{b['font']}", "Liberation Sans", sans-serif;
                color: #{b['text']}; }}
        .slide {{ position: relative; width: 13.333in; height: 7.5in;
                  overflow: hidden; page-break-after: always; }}
        .slide:last-child {{ page-break-after: auto; }}

        .cover {{ background: linear-gradient(135deg,#{b['primary']},#{b['secondary']});
                  color:#fff; }}
        .cover .logo {{ position:absolute; top:.7in; left:.9in; height:.5in; }}
        .cover .logo-text {{ position:absolute; top:.7in; left:.9in;
                  font-weight:800; letter-spacing:.04em; }}
        .cover-body {{ position:absolute; top:2.6in; left:.9in; right:.9in; }}
        .accent-bar {{ width:2.2in; height:.09in; background:#{b['accent']};
                  margin-bottom:.35in; border-radius:2px; }}
        .cover h1 {{ font-size:60pt; font-weight:800; line-height:1.03;
                    letter-spacing:-.01em; }}
        .cover .sub {{ font-size:22pt; margin-top:.3in; color:#dce6f6;
                    max-width:9in; line-height:1.3; }}
        .closing .logo {{ position:absolute; bottom:.7in; left:.9in; height:.45in; }}

        .section {{ background:linear-gradient(135deg,#{b['primary']},#{b['secondary']});
                    color:#fff; display:flex; flex-direction:column;
                    justify-content:center; padding:0 .95in; }}
        .section .secnum {{ position:absolute; top:-.5in; right:.2in;
                    font-size:360pt; font-weight:800; line-height:1;
                    color:rgba(255,255,255,.09); z-index:0; }}
        .section h2 {{ position:relative; z-index:1; font-size:46pt;
                    font-weight:800; border-left:.14in solid #{b['accent']};
                    padding-left:.45in; }}

        .content {{ background:#{b['bg']}; padding:.85in 1in; display:flex;
                    flex-direction:column; justify-content:center; }}
        .content::before {{ content:""; position:absolute; left:0; top:0;
                    width:.28in; height:100%; background:#{b['primary']}; }}
        .head h3 {{ font-size:36pt; font-weight:800; color:#{b['heading']};
                    line-height:1.05; }}
        .rule {{ width:1.8in; height:.07in; background:#{b['accent']};
                    margin-top:.16in; border-radius:2px; }}
        .content > ul {{ margin:.6in 0 0 0; list-style:none; }}
        .content > ul > li {{ font-size:22pt; margin-bottom:.36in;
                    padding-left:.6in; position:relative; line-height:1.3; }}
        .content > ul > li::before {{ content:""; position:absolute; left:0;
                    top:.1in; width:.28in; height:.28in; border-radius:7px;
                    background:#{b['accent']}; }}
        .cols {{ display:flex; gap:.5in; margin-top:.6in; }}
        .col {{ flex:1; background:#{b['card']}; border-radius:12px;
                    padding:.4in .45in; }}
        .col-h {{ color:#{b['heading']}; font-weight:800; font-size:20pt;
                    margin-bottom:.24in; padding-bottom:.16in;
                    border-bottom:.03in solid #{b['accent']}; }}
        .col ul {{ margin:0; list-style:none; }}
        .col li {{ font-size:17pt; margin-bottom:.22in; padding-left:.42in;
                    position:relative; line-height:1.3; }}
        .col li::before {{ content:""; position:absolute; left:0; top:.1in;
                    width:.2in; height:.2in; border-radius:5px;
                    background:#{b['accent']}; }}
        .imgwrap {{ margin-top:.35in; height:4.4in; display:flex;
                    align-items:center; justify-content:center; }}
        .imgwrap img {{ max-width:100%; max-height:100%; border-radius:6px; }}
        .cap {{ text-align:center; color:#{b['muted']}; font-size:12pt;
                    margin-top:.1in; }}

        .imgfull {{ background-size:cover; background-position:center;
                    background-color:#{b['dark']}; }}
        .imgfull .fcap {{ position:absolute; left:0; bottom:0; width:100%;
                    padding:.6in .9in; color:#fff;
                    background:linear-gradient(transparent,#{b['primary']}ee); }}
        .imgfull h3 {{ font-size:30pt; font-weight:800; }}
        .imgfull p {{ font-size:15pt; color:#dce6f6; }}

        .quote {{ background:#{b['light']}; padding:1in 1.2in;
                    display:flex; flex-direction:column; justify-content:center; }}
        .qmark {{ font-size:100pt; color:#{b['accent']}; font-weight:800;
                    line-height:.5; }}
        .quote blockquote {{ font-size:30pt; font-weight:700;
                    color:#{b['primary']}; margin-top:.2in; }}
        .qa {{ margin-top:.4in; font-size:16pt; color:#{b['muted']}; }}

        .foot {{ position:absolute; right:.9in; bottom:.35in;
                    color:#{b['muted']}; font-size:9pt; }}
        '''

    def html(self):
        body = "\n".join(self.slides)
        return (f'<!doctype html><html><head><meta charset="utf-8">'
                f'<style>{self._css()}</style></head><body>{body}</body></html>')

    def save(self, path=None):
        path = path or (self.name + ".pdf")
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        from weasyprint import HTML
        HTML(string=self.html()).write_pdf(path)
        print(f"[gpweb] saved {path} ({len(self.slides)} slides)")
        return path

    def save_html(self, path=None):
        """Write a standalone .html file (self-contained, images inlined)."""
        path = path or (self.name + ".html")
        if not path.lower().endswith(".html"):
            path += ".html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.html())
        print(f"[gpweb] saved {path} ({len(self.slides)} slides)")
        return path
