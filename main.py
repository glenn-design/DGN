import os
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai
from PIL import Image
import io
import base64

app = Flask(__name__)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))


@app.route('/visualiser_prosjekt', methods=['POST'])
def visualiser():
    data = request.json
    beskrivelse = data.get("beskrivelse")
    foto_base64 = data.get("foto_base64")
    foto_url = data.get("foto_url")

    if not foto_base64 and not foto_url:
        return jsonify({"error": "Mangler bilde — send enten foto_base64 eller foto_url"}), 400

    try:
        # Hent og optimaliser bildet
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
            [
                {"mime_type": "image/jpeg", "data": img_b64},
                prompt
            ],
            generation_config={"response_modalities": ["TEXT", "IMAGE"]}
        )

        # Gå gjennom alle parts og finn bildet
        for part in res.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data is not None:
                return jsonify({
                    "visualisering_base64": base64.b64encode(part.inline_data.data).decode("utf-8"),
                    "mime_type": part.inline_data.mime_type
                })

        # Ingen bilde funnet — returner debug-info
        parts_info = []
        for p in res.candidates[0].content.parts:
            parts_info.append(str(type(p)) + ": " + str(dir(p))[:100])
        return jsonify({"error": "Ingen bilde i respons", "debug": parts_info}), 500

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
                    "foto_base64": {
                        "type": "string",
                        "description": "Base64-kodet befaringsfoto uten data:image/jpeg;base64,-prefix"
                    },
                    "beskrivelse": {
                        "type": "string",
                        "description": "Hva som skal gjøres, f.eks. 'ny terrasse i trykkimpregnert tre'"
                    }
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
