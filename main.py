import io
from urllib.parse import unquote, quote

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

app = FastAPI(title="LENS")


@app.get("/")
def root():
    return {
        "name": "LENS",
        "status": "online"
    }


@app.get("/fetch/{target_url:path}")
def fetch(target_url: str):
    url = unquote(target_url)

    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL")

    buffer = io.BytesIO()

    options = {
        "format": "best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "outtmpl": "-",
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)

            requested = info.get("requested_formats")

            if requested:
                raise RuntimeError(
                    "This media requires merging multiple formats"
                )

            media_url = info.get("url")

            if not media_url:
                raise RuntimeError("No media URL found")

        import requests

        response = requests.get(
            media_url,
            stream=True,
            timeout=60
        )
        response.raise_for_status()

        def stream():
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    yield chunk

        return StreamingResponse(
            stream(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": 'inline; filename="lens.mp4"'
            }
        )

    except Exception as e:
        raise HTTPException(
            500,
            f"Extraction failed: {e}"
        )
@app.get("/view/{target_url:path}")
def view(target_url: str):
    url = unquote(target_url)

    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL")

    video_url = "/fetch/" + quote(url, safe="")

    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head>
    <title>LENS Media Viewer</title>
</head>
<body>
    <h1>LENS Media Viewer</h1>

    <video controls width="640">
        <source src="{video_url}" type="video/mp4">
    </video>
</body>
</html>
""")
