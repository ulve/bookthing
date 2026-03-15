from pathlib import Path

import pytest
from fastapi import HTTPException

from app.streaming import get_content_type, parse_range_header


class TestGetContentType:
    def test_mp3(self):
        assert get_content_type(Path("track.mp3")) == "audio/mpeg"

    def test_m4b(self):
        assert get_content_type(Path("book.m4b")) == "audio/mp4"

    def test_m4a(self):
        assert get_content_type(Path("file.m4a")) == "audio/mp4"

    def test_mp4(self):
        assert get_content_type(Path("video.mp4")) == "audio/mp4"

    def test_ogg(self):
        assert get_content_type(Path("file.ogg")) == "audio/ogg"

    def test_flac(self):
        assert get_content_type(Path("file.flac")) == "audio/flac"

    def test_aac(self):
        assert get_content_type(Path("file.aac")) == "audio/aac"

    def test_unknown_extension(self):
        assert get_content_type(Path("file.xyz")) == "application/octet-stream"

    def test_no_extension(self):
        assert get_content_type(Path("noext")) == "application/octet-stream"

    def test_uppercase_extension(self):
        assert get_content_type(Path("TRACK.MP3")) == "audio/mpeg"

    def test_path_with_dirs(self):
        assert get_content_type(Path("/some/dir/book.m4b")) == "audio/mp4"


class TestParseRangeHeader:
    def test_normal_range(self):
        start, end = parse_range_header("bytes=0-999", 10000)
        assert start == 0
        assert end == 999

    def test_open_end(self):
        start, end = parse_range_header("bytes=500-", 1000)
        assert start == 500
        assert end == 999

    def test_suffix_range(self):
        # "bytes=-200" means last 200 bytes
        start, end = parse_range_header("bytes=-200", 1000)
        assert start == 800
        assert end == 999

    def test_full_file_range(self):
        start, end = parse_range_header("bytes=0-", 500)
        assert start == 0
        assert end == 499

    def test_single_byte(self):
        start, end = parse_range_header("bytes=0-0", 100)
        assert start == 0
        assert end == 0

    def test_last_byte(self):
        start, end = parse_range_header("bytes=99-99", 100)
        assert start == 99
        assert end == 99

    def test_invalid_format_raises_416(self):
        with pytest.raises(HTTPException) as exc:
            parse_range_header("invalid", 1000)
        assert exc.value.status_code == 416

    def test_both_empty_raises_416(self):
        with pytest.raises(HTTPException) as exc:
            parse_range_header("bytes=-", 1000)
        assert exc.value.status_code == 416

    def test_start_beyond_file_raises_416(self):
        with pytest.raises(HTTPException) as exc:
            parse_range_header("bytes=2000-3000", 1000)
        assert exc.value.status_code == 416

    def test_end_beyond_file_raises_416(self):
        with pytest.raises(HTTPException) as exc:
            parse_range_header("bytes=0-1000", 1000)
        assert exc.value.status_code == 416

    def test_start_greater_than_end_raises_416(self):
        with pytest.raises(HTTPException) as exc:
            parse_range_header("bytes=500-100", 1000)
        assert exc.value.status_code == 416
