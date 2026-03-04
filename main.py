import os
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai
from PIL import Image
import io
import base64

app = Flask(__name__)

# Konfigurer Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))


@app.route('/visualiser_prosjekt', methods=['POST'])
def visualiser():
    data = request.json
    beskrivelse = data.get("beskrivelse")

    # Støtter både foto_base64 (fra Claude MCP) og foto_url (direkte kall)
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

        # Bygg prompt
        prompt = f"""Du er en profesjonell arkitektvisualisering-AI.
Basert på befaringsbildet, generer en fotorealistisk visualisering av det ferdige resultatet etter dette arbeidet:

{beskrivelse}

Behold samme perspektiv, kameravinkel og omgivelser som i originalbildet.
Resultatet skal se ut som et ekte fotografi — ikke en tegning eller illustrasjon."""

        # Bruk Gemini bildegenereringsmodell
        model = genai.GenerativeModel('gemini-2.0-flash-exp-image-generation')
        res = model.generate_content(
            [
                prompt,
                {"mime_type": "image/jpeg", "data": img_b64}
            ],
            generation_config={"response_modalities": ["image"]}
        )

        # Hent ut generert bilde
        for part in res.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                return jsonify({
                    "visualisering_base64": part.inline_data.data,
                    "mime_type": part.inline_data.mime_type
                })

        return jsonify({"error": "Ingen bilde generert — prøv med en annen beskrivelse"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/sse')
def sse():
    """MCP tool discovery endpoint"""
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
                        "description": "Hva som skal gjøres, f.eks. 'ny kledning i hvit trepanel, ny terrasse'"
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
