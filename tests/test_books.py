import json

import pytest

import app.books as books_module


class TestGetBookList:
    def test_returns_visible_books(self, temp_metadata):
        result = books_module.get_book_list()
        ids = [b["book_id"] for b in result]
        assert "book1" in ids
        assert "book2" in ids

    def test_excludes_hidden(self, temp_metadata):
        result = books_module.get_book_list()
        assert not any(b["book_id"] == "hidden_book" for b in result)

    def test_excludes_missing(self, temp_metadata):
        result = books_module.get_book_list()
        assert not any(b["book_id"] == "missing_book" for b in result)

    def test_search_by_title(self, temp_metadata):
        result = books_module.get_book_list(search="test book")
        assert len(result) == 1
        assert result[0]["book_id"] == "book1"

    def test_search_by_author(self, temp_metadata):
        result = books_module.get_book_list(search="another author")
        assert len(result) == 1
        assert result[0]["book_id"] == "book2"

    def test_search_case_insensitive(self, temp_metadata):
        result = books_module.get_book_list(search="TEST")
        assert any(b["book_id"] == "book1" for b in result)

    def test_search_no_match(self, temp_metadata):
        result = books_module.get_book_list(search="zzznomatch")
        assert result == []

    def test_filter_by_author(self, temp_metadata):
        result = books_module.get_book_list(author="Test Author")
        assert len(result) == 1
        assert result[0]["book_id"] == "book1"

    def test_filter_by_author_case_insensitive(self, temp_metadata):
        result = books_module.get_book_list(author="test author")
        assert len(result) == 1

    def test_filter_by_series(self, temp_metadata):
        result = books_module.get_book_list(series="Test Series")
        assert len(result) == 1
        assert result[0]["book_id"] == "book1"

    def test_filter_by_tags(self, temp_metadata):
        result = books_module.get_book_list(tags="fantasy")
        assert len(result) == 1
        assert result[0]["book_id"] == "book1"

    def test_filter_by_multiple_tags(self, temp_metadata):
        result = books_module.get_book_list(tags="fantasy,sci-fi")
        ids = [b["book_id"] for b in result]
        assert "book1" in ids
        assert "book2" in ids

    def test_sorted_by_author_title(self, temp_metadata):
        result = books_module.get_book_list(sort="author")
        authors = [b["author"] for b in result]
        assert authors == sorted(authors)

    def test_summary_fields_present(self, temp_metadata):
        result = books_module.get_book_list()
        book = next(b for b in result if b["book_id"] == "book1")
        assert "book_id" in book
        assert "title" in book
        assert "author" in book
        assert "tags" in book
        assert "has_cover" in book
        assert "file_count" in book

    def test_empty_metadata(self, tmp_path, monkeypatch):
        meta_file = tmp_path / "metadata.json"
        meta_file.write_text(json.dumps({"books": {}}))
        monkeypatch.setattr("app.books.METADATA_PATH", meta_file)
        assert books_module.get_book_list() == []


class TestGetAuthors:
    def test_returns_unique_authors(self, temp_metadata):
        result = books_module.get_authors()
        assert "Test Author" in result
        assert "Another Author" in result

    def test_excludes_missing_books(self, temp_metadata):
        result = books_module.get_authors()
        assert "Gone Author" not in result

    def test_sorted(self, temp_metadata):
        result = books_module.get_authors()
        assert result == sorted(result)

    def test_no_duplicates(self, temp_metadata):
        result = books_module.get_authors()
        assert len(result) == len(set(result))


class TestGetSeriesList:
    def test_returns_series(self, temp_metadata):
        result = books_module.get_series_list()
        assert "Test Series" in result

    def test_excludes_none_series(self, temp_metadata):
        result = books_module.get_series_list()
        assert None not in result

    def test_sorted(self, temp_metadata):
        result = books_module.get_series_list()
        assert result == sorted(result)


class TestGetTagsList:
    def test_returns_tags(self, temp_metadata):
        result = books_module.get_tags_list()
        assert "fantasy" in result
        assert "adventure" in result
        assert "sci-fi" in result

    def test_sorted(self, temp_metadata):
        result = books_module.get_tags_list()
        assert result == sorted(result)

    def test_no_duplicates(self, temp_metadata):
        result = books_module.get_tags_list()
        assert len(result) == len(set(result))


class TestUpdateBook:
    def test_update_title(self, temp_metadata):
        ok = books_module.update_book("book1", {"title": "New Title"})
        assert ok is True
        book = books_module.get_book_detail("book1")
        assert book["title"] == "New Title"

    def test_update_author(self, temp_metadata):
        books_module.update_book("book1", {"author": "New Author"})
        book = books_module.get_book_detail("book1")
        assert book["author"] == "New Author"

    def test_update_tags(self, temp_metadata):
        books_module.update_book("book1", {"tags": ["new-tag"]})
        book = books_module.get_book_detail("book1")
        assert book["tags"] == ["new-tag"]

    def test_update_hidden(self, temp_metadata):
        books_module.update_book("book1", {"hidden": True})
        # hidden books don't appear in get_book_list
        result = books_module.get_book_list()
        assert not any(b["book_id"] == "book1" for b in result)

    def test_unknown_book_returns_false(self, temp_metadata):
        ok = books_module.update_book("nonexistent", {"title": "x"})
        assert ok is False

    def test_unknown_field_ignored(self, temp_metadata):
        ok = books_module.update_book("book1", {"malicious_field": "value"})
        assert ok is True
        data = books_module.load_metadata()
        assert "malicious_field" not in data["books"]["book1"]


class TestBulkUpdateBooks:
    def test_update_author_on_multiple(self, temp_metadata):
        count = books_module.bulk_update_books(["book1", "book2"], {"author": "Bulk Author"})
        assert count == 2
        assert books_module.get_book_detail("book1")["author"] == "Bulk Author"
        assert books_module.get_book_detail("book2")["author"] == "Bulk Author"

    def test_skips_nonexistent_ids(self, temp_metadata):
        count = books_module.bulk_update_books(["book1", "nonexistent"], {"author": "X"})
        assert count == 1

    def test_tags_replace_mode(self, temp_metadata):
        books_module.bulk_update_books(["book1"], {"tags": ["new"]}, tags_mode="replace")
        book = books_module.get_book_detail("book1")
        assert book["tags"] == ["new"]

    def test_tags_add_mode_merges(self, temp_metadata):
        books_module.bulk_update_books(["book1"], {"tags": ["extra"]}, tags_mode="add")
        book = books_module.get_book_detail("book1")
        assert "fantasy" in book["tags"]
        assert "extra" in book["tags"]

    def test_empty_list_returns_zero(self, temp_metadata):
        count = books_module.bulk_update_books([], {"author": "X"})
        assert count == 0


class TestDeleteBook:
    def test_deletes_existing(self, temp_metadata):
        ok = books_module.delete_book("book1")
        assert ok is True
        assert books_module.get_book_detail("book1") is None

    def test_missing_book_returns_false(self, temp_metadata):
        ok = books_module.delete_book("nonexistent")
        assert ok is False
