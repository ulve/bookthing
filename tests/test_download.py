import io
import urllib.parse
import zipfile


class TestDownloadAuth:
    def test_download_requires_auth(self, client):
        resp = client.get("/api/download/book1")
        assert resp.status_code == 401

    def test_download_unknown_book_returns_404(self, auth_client):
        resp = auth_client.get("/api/download/nonexistent")
        assert resp.status_code == 404


class TestDownloadSingleFile:
    def test_single_file_filename(self, auth_client, tmp_path, monkeypatch):
        audio_file = tmp_path / "audiobooks" / "book2" / "file.m4b"
        audio_file.parent.mkdir(parents=True)
        audio_file.write_bytes(b"\x00" * 64)

        resp = auth_client.get("/api/download/book2")
        assert resp.status_code == 200
        disposition = urllib.parse.unquote(resp.headers["content-disposition"])
        assert "Another Author - Another Book.m4b" in disposition

    def test_single_file_content_type(self, auth_client, tmp_path, monkeypatch):
        audio_file = tmp_path / "audiobooks" / "book2" / "file.m4b"
        audio_file.parent.mkdir(parents=True, exist_ok=True)
        audio_file.write_bytes(b"\x00" * 64)

        resp = auth_client.get("/api/download/book2")
        assert resp.status_code == 200
        assert "audio/mp4" in resp.headers["content-type"]

    def test_single_file_is_attachment(self, auth_client, tmp_path):
        audio_file = tmp_path / "audiobooks" / "book2" / "file.m4b"
        audio_file.parent.mkdir(parents=True, exist_ok=True)
        audio_file.write_bytes(b"\x00" * 64)

        resp = auth_client.get("/api/download/book2")
        assert "attachment" in resp.headers["content-disposition"]


class TestDownloadMultiFile:
    def _make_multifile_book(self, tmp_path, monkeypatch):
        import json
        from tests.conftest import SAMPLE_METADATA

        meta = {
            "books": {
                **SAMPLE_METADATA["books"],
                "multibook": {
                    "book_id": "multibook",
                    "title": "Long Story",
                    "author": "Some Author",
                    "tags": [],
                    "files": ["multibook/part1.mp3", "multibook/part2.mp3"],
                    "file_durations": [3600.0, 3600.0],
                },
            }
        }
        meta_file = tmp_path / "metadata.json"
        meta_file.write_text(json.dumps(meta))
        monkeypatch.setattr("app.books.METADATA_PATH", meta_file)

        for name in ("part1.mp3", "part2.mp3"):
            f = tmp_path / "audiobooks" / "multibook" / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"\x00" * 64)

    def test_zip_filename(self, auth_client, tmp_path, monkeypatch):
        self._make_multifile_book(tmp_path, monkeypatch)
        resp = auth_client.get("/api/download/multibook")
        assert resp.status_code == 200
        disposition = urllib.parse.unquote(resp.headers["content-disposition"])
        assert "Some Author - Long Story.zip" in disposition

    def test_zip_content_type(self, auth_client, tmp_path, monkeypatch):
        self._make_multifile_book(tmp_path, monkeypatch)
        resp = auth_client.get("/api/download/multibook")
        assert "application/zip" in resp.headers["content-type"]

    def test_zip_contains_both_files(self, auth_client, tmp_path, monkeypatch):
        self._make_multifile_book(tmp_path, monkeypatch)
        resp = auth_client.get("/api/download/multibook")
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = zf.namelist()
        assert "part1.mp3" in names
        assert "part2.mp3" in names
