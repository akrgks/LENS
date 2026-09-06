import io
import os
import uuid
from urllib.parse import unquote, quote

import imageio_ffmpeg
import requests
import yt_dlp

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse

app = FastAPI(title="LENS")

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


@app.get("/")
def root():
    return {
        "name": "LENS",
        "status": "online"
    }


# ---------------------------------------------------------
# Direct video streaming
# ---------------------------------------------------------

@app.get("/fetch/{target_url:path}")
def fetch(target_url: str):
    url = unquote(target_url)

    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL")

    try:
        options = {
            "format": "best[ext=mp4]/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)

            if info.get("requested_formats"):
                raise RuntimeError(
                    "This media requires merging multiple formats"
                )

            media_url = info.get("url")

            if not media_url:
                raise RuntimeError("No media URL found")

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


# ---------------------------------------------------------
# HTML + ALL FRAMES AT HALF FPS
# ---------------------------------------------------------

@app.get("/view/{target_url:path}")
def view(target_url: str):
    url = unquote(target_url)

    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL")

    job_id = uuid.uuid4().hex

    workdir = os.path.join("/tmp", "lens", job_id)
    frames_dir = os.path.join(workdir, "frames")

    os.makedirs(frames_dir, exist_ok=True)

    video_path = os.path.join(workdir, "video.mp4")

    try:
        # -------------------------------------------------
        # Download video with yt-dlp
        # -------------------------------------------------

        options = {
            "format": "best[ext=mp4]/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": video_path,
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)

        # Get FPS from yt-dlp metadata
        fps = info.get("fps")

        if not fps or fps <= 0:
            fps = 30.0

        # Half the original FPS
        sample_fps = max(fps / 2.0, 1.0)

        # -------------------------------------------------
        # Extract frames
        # -------------------------------------------------

        output_pattern = os.path.join(
            frames_dir,
            "frame_%06d.jpg"
        )

        command = [
            FFMPEG,
            "-y",
            "-i",
            video_path,
            "-vf",
            f"fps={sample_fps}",
            "-q:v",
            "3",
            output_pattern,
        ]

        import subprocess

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "FFmpeg failed:\n" + result.stderr[-2000:]
            )

        # -------------------------------------------------
        # Find generated frames
        # -------------------------------------------------

        frame_files = sorted(
            filename
            for filename in os.listdir(frames_dir)
            if filename.lower().endswith(".jpg")
        )

        if not frame_files:
            raise RuntimeError("No frames were generated")

        # -------------------------------------------------
        # Build HTML
        # -------------------------------------------------

        images = "\n".join(
            f'''
            <img
                src="/frame/{job_id}/{quote(filename)}"
                loading="eager"
                style="max-width:640px;display:block;margin:10px 0;"
            >
            '''
            for filename in frame_files
        )

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>LENS Frame Viewer</title>
</head>

<body>

<h1>LENS Frame Viewer</h1>

<p>
    Original FPS: {fps:.2f}<br>
    Sample FPS: {sample_fps:.2f}<br>
    Frames: {len(frame_files)}
</p>

<hr>

{images}

</body>
</html>
"""

        return HTMLResponse(html)

    except Exception as e:
        raise HTTPException(
            500,
            f"Frame extraction failed: {e}"
        )


# ---------------------------------------------------------
# Individual frame endpoint
# ---------------------------------------------------------

@app.get("/frame/{job_id}/{filename}")
def frame(job_id: str, filename: str):

    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")

    path = os.path.join(
        "/tmp",
        "lens",
        job_id,
        "frames",
        filename
    )

    if not os.path.isfile(path):
        raise HTTPException(
            404,
            "Frame not found"
        )

    return FileResponse(
        path,
        media_type="image/jpeg"
    )
