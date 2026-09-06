import io
from urllib.parse import unquote, quote

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import os
import subprocess
import tempfile
import uuid
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse

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

    job_id = uuid.uuid4().hex
    workdir = os.path.join("/tmp", job_id)
    os.makedirs(workdir, exist_ok=True)

    video_path = os.path.join(workdir, "video.mp4")
    frames_dir = os.path.join(workdir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    try:
        # Download the Reel
        options = {
            "format": "best[ext=mp4]/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": video_path,
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

        # Get original FPS
        probe = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        fps_text = probe.stdout.strip()

        # Convert FPS fraction like 30/1
        num, den = map(int, fps_text.split("/"))
        fps = num / den

        # Half the original frame rate
        sample_fps = max(fps / 2, 1)

        # Extract frames
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-vf", f"fps={sample_fps}",
                "-q:v", "3",
                os.path.join(frames_dir, "frame_%06d.jpg"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Build HTML
        frame_files = sorted(os.listdir(frames_dir))

        images = "\n".join(
            f'<img src="/frame/{job_id}/{filename}" loading="eager">'
            for filename in frame_files
        )

        return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head>
    <title>LENS Frame Viewer</title>
</head>

<body>
    <h1>LENS Frame Viewer</h1>

    <p>
        Original FPS: {fps:.2f}<br>
        Sample FPS: {sample_fps:.2f}<br>
        Frames: {len(frame_files)}
    </p>

    {images}

</body>
</html>
""")

    except Exception as e:
        raise HTTPException(500, f"Frame extraction failed: {e}")


@app.get("/frame/{job_id}/{filename}")
def frame(job_id: str, filename: str):
    path = os.path.join("/tmp", job_id, "frames", filename)

    if not os.path.isfile(path):
        raise HTTPException(404, "Frame not found")

    return FileResponse(path, media_type="image/jpeg")
