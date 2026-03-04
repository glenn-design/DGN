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
    foto_url = data.get("foto_url")
    beskrivelse = data.get("beskrivelse")

    if not foto_url:
        return jsonify({"error": "Mangler bilde-URL"}), 400

    try:
        # Serveren henter bildet direkte fra nettet
        response = requests.get(foto_url)
        img = Image.open(io.BytesIO(response.content))
        
        # Optimaliserer bildet internt
        img.thumbnail((1024, 1024))
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        # Sender til Gemini (Nano Banana 2)
        model = genai.GenerativeModel('gemini-3-flash-image')
        res = model.generate_content([
            beskrivelse,
            {"mime_type": "image/jpeg", "data": img_str}
        ])

        return jsonify({"visualisering": res.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/sse')
def sse():
    return jsonify({
        "tools": [{
            "name": "visualiser_prosjekt",
            "description": "Visualiserer bygg ved hjelp av en bilde-URL.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "foto_url": {"type": "string", "description": "Direktelenke til bildet (f.eks. fra Imgur)"},
                    "beskrivelse": {"type": "string"}
                },
                "required": ["foto_url", "beskrivelse"]
            }
        }]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
