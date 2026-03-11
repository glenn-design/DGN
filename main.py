import os
import requests
from flask import Flask, request, jsonify, send_file
import google.generativeai as genai
from PIL import Image
import io
import base64
import tempfile
import anthropic
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
import json

app = Flask(__name__)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# ─────────────────────────────────────────────────────────────
# DGN BRAND CONSTANTS
# ─────────────────────────────────────────────────────────────
BLACK      = RGBColor(0x11, 0x11, 0x11)
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
DARK       = RGBColor(0x1E, 0x1E, 0x1E)
MID        = RGBColor(0x55, 0x55, 0x55)
LIGHT      = RGBColor(0x88, 0x88, 0x88)
SURFACE    = RGBColor(0xF2, 0xF2, 0xF2)
ULTRALIGHT = RGBColor(0xCC, 0xCC, 0xCC)

FONT = "Calibri"

def px(inches): return Inches(inches)
def add_rect(slide, x, y, w, h, fill_color, line_color=None):
    shape = slide.shapes.add_shape(1, px(x), px(y), px(w), px(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.color.rgb = line_color or fill_color
    return shape

def add_text(slide, text, x, y, w, h, size=13, bold=False, color=None, align=PP_ALIGN.LEFT, italic=False):
    txBox = slide.shapes.add_textbox(px(x), px(y), px(w), px(h))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color or MID
    return txBox

def add_label(slide, text, x, y, w):
    add_text(slide, text.upper(), x, y, w, 0.25, size=8, bold=True, color=LIGHT)

def add_divider(slide, x, y, w):
    line = slide.shapes.add_shape(1, px(x), px(y), px(w), px(0.01))
    line.fill.solid()
    line.fill.fore_color.rgb = ULTRALIGHT
    line.line.color.rgb = ULTRALIGHT

# ─────────────────────────────────────────────────────────────
# AI: GENERER TILBUDSTEKST
# ─────────────────────────────────────────────────────────────
def generer_tilbudstekst(input_data):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = f"""Du er tilbudsassistent for Den Gode Nabo (DGN), et snekker/håndverksfirma i Drøbak.

Generer tilbudstekst basert på dette:
- Kunde: {input_data.get('kunde_navn', 'Kunde')}
- Prosjekttype: {input_data.get('prosjekt_type', 'Ukjent')}
- Beskrivelse: {input_data.get('beskrivelse', '')}
- Pris: {input_data.get('pris', '')} kr eks. mva.
- Tidsramme: {input_data.get('tidsramme', '')}
- Ekstra notater: {input_data.get('notater', '')}

Tone of Voice: Profesjonell men varm. Konkret og tillitsvekkende. Norsk håndverkstradisjon.

Svar KUN med JSON i dette formatet (ingen annen tekst):
{{
  "ingress": "2-3 setninger som åpner tilbudet varmt og konkret",
  "scope": "Hva jobben inkluderer, 2-4 punkter som streng med linjeskift",
  "materialer": "Materialvalg og kvalitet, 1-2 setninger",
  "garanti": "Kort setning om garanti/ettervern",
  "avslutning": "Vennlig avslutningssetning"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


# ─────────────────────────────────────────────────────────────
# PPTX BUILDER
# ─────────────────────────────────────────────────────────────
def bygg_tilbud_pptx(input_data, tekst):
    prs = Presentation()
    prs.slide_width  = Inches(10)
    prs.slide_height = Inches(5.625)
    blank = prs.slide_layouts[6]  # Blank layout

    kunde       = input_data.get("kunde_navn", "Kunde")
    prosjekt    = input_data.get("prosjekt_type", "Prosjekt")
    pris        = input_data.get("pris", "")
    tidsramme   = input_data.get("tidsramme", "")
    dato        = input_data.get("dato", "2026")
    adresse     = input_data.get("adresse", "")

    # ── SLIDE 1: COVER ──────────────────────────────────────
    s1 = prs.slides.add_slide(blank)
    add_rect(s1, 0, 0, 10, 5.625, WHITE)
    add_rect(s1, 4.8, 0, 5.2, 5.625, DARK)

    logo_path = "/app/dgn_logo.png"
    if os.path.exists(logo_path):
        s1.shapes.add_picture(logo_path, px(0.6), px(1.2), px(2.2), px(2.24))
    else:
        add_text(s1, "dgn", 0.6, 1.2, 3.5, 1.8, size=72, bold=True, color=BLACK)
    add_text(s1, prosjekt, 0.65, 3.7, 3.8, 0.4,
             size=13, color=LIGHT)
    add_text(s1, dato, 0.65, 5.1, 3.5, 0.3,
             size=8, bold=True, color=LIGHT)

    # ── SLIDE 2: PROSJEKTDATA ────────────────────────────────
    s2 = prs.slides.add_slide(blank)
    add_rect(s2, 0, 0, 10, 5.625, WHITE)

    add_text(s2, "Prosjektdata", 0.6, 2.0, 3.8, 1.0,
             size=32, color=BLACK)

    fields = [
        ("KUNDE",      kunde),
        ("PROSJEKT",   prosjekt),
        ("ADRESSE",    adresse or "—"),
        ("DATO",       dato),
    ]
    yy = 0.5
    for label, value in fields:
        add_divider(s2, 4.8, yy, 5.0)
        yy += 0.15
        add_label(s2, label, 4.8, yy, 5.0)
        yy += 0.27
        add_text(s2, value, 4.8, yy, 5.0, 0.3, size=12, color=MID)
        yy += 0.45
    add_divider(s2, 4.8, yy, 5.0)

    # ── SLIDE 3: INGRESS ─────────────────────────────────────
    s3 = prs.slides.add_slide(blank)
    add_rect(s3, 0, 0, 10, 5.625, WHITE)

    add_text(s3, "Tilbud", 0.6, 0.7, 9.0, 0.7,
             size=32, color=BLACK)
    add_divider(s3, 0.6, 1.55, 8.8)
    add_text(s3, tekst.get("ingress", ""), 0.6, 1.75, 8.8, 2.0,
             size=13, color=MID)

    # ── SLIDE 4: OMFANG ──────────────────────────────────────
    s4 = prs.slides.add_slide(blank)
    add_rect(s4, 0, 0, 10, 5.625, WHITE)
    add_rect(s4, 0, 0, 4.4, 5.625, SURFACE)

    add_label(s4, "OMFANG", 4.8, 0.45, 5.0)
    add_text(s4, "Hva jobben inkluderer", 4.8, 0.75, 5.0, 0.6,
             size=22, color=BLACK)

    scope_lines = tekst.get("scope", "").split("\n")
    yy = 1.55
    for line in scope_lines:
        if line.strip():
            add_text(s4, f"— {line.strip()}", 4.8, yy, 4.9, 0.35,
                     size=12, color=MID)
            yy += 0.4

    add_text(s4, tekst.get("materialer", ""), 0.4, 2.2, 3.6, 1.5,
             size=11, color=LIGHT, italic=True)

    # ── SLIDE 5: PRIS ────────────────────────────────────────
    s5 = prs.slides.add_slide(blank)
    add_rect(s5, 0, 0, 10, 5.625, WHITE)
    add_rect(s5, 5.8, 0, 4.2, 5.625, SURFACE)

    add_text(s5, "Pris og\nbetingelser", 0.6, 1.8, 4.8, 1.5,
             size=32, color=BLACK)

    price_items = [
        ("Fastpris",      f"{pris} kr eks. mva." if pris else "—"),
        ("Tidsramme",     tidsramme or "—"),
        ("Faktura",       "100% ved leveranse"),
        ("Garanti",       tekst.get("garanti", "—")),
    ]
    yy = 0.6
    for label, value in price_items:
        add_text(s5, label, 6.1, yy, 3.7, 0.28,
                 size=11, bold=True, color=BLACK)
        yy += 0.3
        add_text(s5, value, 6.1, yy, 3.7, 0.3,
                 size=11, color=MID)
        yy += 0.65

    # ── SLIDE 6: AVSLUTNING ──────────────────────────────────
    s6 = prs.slides.add_slide(blank)
    add_rect(s6, 0, 0, 10, 5.625, DARK)

    add_text(s6, tekst.get("avslutning", "Takk for oppdraget."),
             1.0, 2.0, 8.0, 1.0,
             size=18, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(s6, "dengodanabo.no",
             1.0, 4.9, 8.0, 0.4,
             size=9, color=LIGHT, align=PP_ALIGN.CENTER)

    # ── SKRIV TIL BUFFER ─────────────────────────────────────
    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────────────────────
# ENDEPUNKT: /generer-tilbud
# ─────────────────────────────────────────────────────────────
@app.route('/generer-tilbud', methods=['POST'])
def generer_tilbud():
    """
    Input (JSON):
      kunde_navn    str   — "Fru Hansen"
      prosjekt_type str   — "Platting", "Tilbygg", "Carport" etc.
      beskrivelse   str   — fritekst fra befaring
      pris          str   — "45000"
      tidsramme     str   — "3-4 uker"
      dato          str   — "Mars 2026"
      adresse       str   — "Storgata 12, Drøbak"
      notater       str   — ekstra stikkord

    Output:
      .pptx fil som nedlasting
    """
    data = request.json
    if not data:
        return jsonify({"error": "Mangler JSON-body"}), 400

    required = ["kunde_navn", "prosjekt_type", "beskrivelse"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Mangler felt: {field}"}), 400

    try:
        # 1. Generer tekst med Claude
        tekst = generer_tilbudstekst(data)

        # 2. Bygg PPTX
        pptx_buf = bygg_tilbud_pptx(data, tekst)

        # 3. Returner filen
        filnavn = f"DGN_Tilbud_{data['kunde_navn'].replace(' ', '_')}.pptx"
        return send_file(
            pptx_buf,
            mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            as_attachment=True,
            download_name=filnavn
        )

    except json.JSONDecodeError as e:
        return jsonify({"error": f"AI returnerte ugyldig JSON: {str(e)}"}), 500
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


# ─────────────────────────────────────────────────────────────
# EKSISTERENDE ENDEPUNKTER (urørt)
# ─────────────────────────────────────────────────────────────
@app.route('/visualiser_prosjekt', methods=['POST'])
def visualiser():
    data = request.json
    beskrivelse = data.get("beskrivelse")
    foto_base64 = data.get("foto_base64")
    foto_url = data.get("foto_url")

    if not foto_base64 and not foto_url:
        return jsonify({"error": "Mangler bilde — send enten foto_base64 eller foto_url"}), 400

    try:
        if foto_base64:
            img_bytes = base64.b64decode(foto_base64)
        else:
            response = requests.get(foto_url, timeout=10)
            response.raise_for_status()
            img_bytes = response.content

        img = Image.open(io.BytesIO(img_bytes))
        img.thumbnail((1024, 1024))
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode()

        prompt = f"""Generer en fotorealistisk visualisering av dette byggeprosjektet etter ferdigstillelse:

{beskrivelse}

Behold samme perspektiv og kameravinkel som i befaringsbildet.
Resultatet skal se ut som et ekte fotografi."""

        model = genai.GenerativeModel('gemini-2.0-flash-exp-image-generation')
        res = model.generate_content(
            [{"mime_type": "image/jpeg", "data": img_b64}, prompt],
            generation_config={"response_modalities": ["TEXT", "IMAGE"]}
        )

        for part in res.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data is not None:
                raw = part.inline_data.data
                mime = part.inline_data.mime_type
                if isinstance(raw, bytes):
                    img_out = base64.b64encode(raw).decode("utf-8")
                elif isinstance(raw, str):
                    img_out = raw
                else:
                    continue
                if img_out:
                    return jsonify({"visualisering_base64": img_out, "mime_type": mime})

        parts_debug = []
        for p in res.candidates[0].content.parts:
            if hasattr(p, 'inline_data') and p.inline_data:
                parts_debug.append({"type": str(type(p.inline_data.data)), "len": len(p.inline_data.data) if p.inline_data.data else 0, "mime": p.inline_data.mime_type})
            elif hasattr(p, 'text'):
                parts_debug.append({"text": p.text[:200]})
        return jsonify({"error": "Ingen bilde i respons", "debug": parts_debug}), 500

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@app.route('/sse')
def sse():
    return jsonify({
        "tools": [{
            "name": "visualiser_prosjekt",
            "description": "Tar inn befaringsfoto og prosjektbeskrivelse, returnerer fotorealistisk visualisering av ferdig prosjekt.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "foto_base64": {"type": "string", "description": "Base64-kodet befaringsfoto uten data:image/jpeg;base64,-prefix"},
                    "beskrivelse": {"type": "string", "description": "Hva som skal gjøres, f.eks. 'ny terrasse i trykkimpregnert tre'"}
                },
                "required": ["foto_base64", "beskrivelse"]
            }
        }]
    })


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
