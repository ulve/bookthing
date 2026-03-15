import re
from pathlib import Path
import aiofiles
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

CHUNK_SIZE = 65536

CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4b": "audio/mp4",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
}


def get_content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int]:
    match = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not match:
        raise HTTPException(status_code=416, detail="Invalid range")
    start_str, end_str = match.group(1), match.group(2)
    if start_str == "" and end_str == "":
        raise HTTPException(status_code=416, detail="Invalid range")
    if start_str == "":
        # suffix range: last N bytes
        start = file_size - int(end_str)
        end = file_size - 1
    elif end_str == "":
        start = int(start_str)
        end = file_size - 1
    else:
        start = int(start_str)
        end = int(end_str)

    if start < 0 or end >= file_size or start > end:
        raise HTTPException(
            status_code=416,
            headers={"Content-Range": f"bytes */{file_size}"},
            detail="Range not satisfiable",
        )
    return start, end


async def stream_audio(file_path: Path, range_header: str | None) -> StreamingResponse:
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    file_size = file_path.stat().st_size
    content_type = get_content_type(file_path)

    if range_header:
        start, end = parse_range_header(range_header, file_size)
        status_code = 206
    else:
        start, end = 0, file_size - 1
        status_code = 200

    content_length = end - start + 1

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Type": content_type,
    }

    async def generator():
        async with aiofiles.open(file_path, "rb") as f:
            await f.seek(start)
            remaining = content_length
            while remaining > 0:
                chunk = await f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(generator(), status_code=status_code, headers=headers, media_type=content_type)
