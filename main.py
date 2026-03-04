import os
import base64
from flask import Flask, request, jsonify
import google.generativeai as genai
from PIL import Image
import io

app = Flask(__name__)

# Konfigurer Gemini med nøkkelen fra Railway
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def resize_image(base64_str, max_size=(800, 800)):
    # Denne funksjonen fikser "32000 token"-feilen ved å krympe bildet før sending
    try:
        # Fjerner header hvis den finnes (f.eks. data:image/jpeg;base64,)
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]
            
        img_data = base64.b64decode(base64_str)
        img = Image.open(io.BytesIO(img_data))
        
        # Konverter til RGB (viktig hvis bildet er PNG/RGBA)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"Resize error: {e}")
        return base64_str

@app.route('/visualiser_prosjekt', methods=['POST'])
def visualiser():
    data = request.json
    foto_base64 = data.get("foto_base64")
    beskrivelse = data.get("beskrivelse")

    if not foto_base64:
        return jsonify({"error": "Mangler bilde"}), 400

    # Krymper bildet før det sendes til Google for å spare tokens
    optimalisert_bilde = resize_image(foto_base64)

    # Bruker korrekt modellnavn: gemini-3-flash-image (Nano Banana 2)
    model = genai.GenerativeModel('gemini-3-flash-image')
    
    try:
        response = model.generate_content([
            beskrivelse,
            {"mime_type": "image/jpeg", "data": optimalisert_bilde}
        ])
        return jsonify({"visualisering": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/sse')
def sse():
    # Dette forteller Claude hvilke verktøy som er tilgjengelige
    return jsonify({
        "tools": [{
            "name": "visualiser_prosjekt",
            "description": "Lager fotorealistiske visualiseringer av byggeprosjekter basert på befaringsfoto.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "foto_base64": {"type": "string", "description": "Base64-strengen av bildet"},
                    "beskrivelse": {"type": "string", "description": "Arkitektonisk beskrivelse av endringene"}
                },
                "required": ["foto_base64", "beskrivelse"]
            }
        }]
    })

if __name__ == "__main__":
    # Kjører på porten Railway tildeler (standard 8080)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
