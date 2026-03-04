import os
import httpx
import uvicorn
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route

# Henter API-nøkkel fra Railway sine miljøvariabler
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# Oppdatert til den nyeste Gemini 3 Flash Image-modellen for bildegenerering/redigering
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-image:generateContent"

server = Server("nanobanana-mcp")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="visualiser_prosjekt",
            description="Tar inn befaringsfoto og prosjektbeskrivelse, returnerer visualisering av ferdig prosjekt",
            inputSchema={
                "type": "object",
                "properties": {
                    "foto_base64": {"type": "string", "description": "Base64-kodet befaringsfoto uten data:image/jpeg;base64,-prefix"},
                    "beskrivelse": {"type": "string", "description": "Hva som skal gjøres, f.eks. 'ny kledning i hvit trepanel, ny terrasse'"}
                },
                "required": ["foto_base64", "beskrivelse"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name != "visualiser_prosjekt":
        raise ValueError(f"Ukjent verktøy: {name}")

    if not GEMINI_API_KEY:
        return [TextContent(type="text", text="Feil: GEMINI_API_KEY mangler i systemet.")]

    prompt = f"""Dette er et befaringsfoto fra et byggprosjekt. Generer et fotorealistisk bilde som viser hvordan eiendommen vil se ut etter at følgende arbeid er utført:
{arguments['beskrivelse']}
Behold samme vinkel, lys og omgivelser som originalfotot. Gjør endringene realistiske og profesjonelle."""

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {
                    "mime_type": "image/jpeg",
                    "data": arguments["foto_base64"]
                }}
            ]
        }],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{API_URL}?key={GEMINI_API_KEY}",
            json=payload
        )
        r.raise_for_status()
        data = r.json()

    # Hent bildedata fra respons
    for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            return [ImageContent(
                type="image",
                data=part["inlineData"]["data"],
                mimeType=part["inlineData"]["mimeType"]
            )]

    return [TextContent(type="text", text="Kunne ikke generere bilde")]

# --- Web Server Oppsett for Railway (SSE) ---
transport = SseServerTransport("/messages")

async def handle_sse(request):
    async with transport.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

async def handle_messages(request):
    await transport.handle_post_message(request.scope, request.receive, request._send)

app = Starlette(routes=[
    Route("/sse", endpoint=handle_sse),
    Route("/messages", endpoint=handle_messages, methods=["POST"])
])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
