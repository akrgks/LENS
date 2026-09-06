import uuid
from pathlib import Path
from urllib.parse import urlparse
from fastapi import Request
import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI(title="LENS")

DOWNLOAD_DIR = Path("/tmp/lens")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


@app.get("/")
def root():
    return {
        "name": "LENS",
        "status": "online"
    }


@app.get("/fetch")
def fetch(url: str, request: Request):
    if not is_valid_url(url):
        raise HTTPException(400, "Invalid URL")

    file_id = uuid.uuid4().hex
    output = DOWNLOAD_DIR / f"{file_id}.%(ext)s"

    options = {
        "outtmpl": str(output),
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)

    except Exception as e:
        raise HTTPException(
            500,
            f"Extraction failed: {e}"
        )

    files = list(DOWNLOAD_DIR.glob(f"{file_id}.*"))

    if not files:
        raise HTTPException(500, "Media file was not created")

    return {
        "success": True,
        "id": file_id,
        "title": info.get("title"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader"),
        "video": str(request.base_url) + f"media/{files[0].name}"
    }


@app.get("/media/{filename}")
def media(filename: str):
    file = DOWNLOAD_DIR / filename

    if not file.exists() or file.parent != DOWNLOAD_DIR:
        raise HTTPException(404, "Media not found")

    return FileResponse(
        file,
        media_type="video/mp4",
        filename="lens_media.mp4"
    )
