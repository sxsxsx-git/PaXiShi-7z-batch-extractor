from pathlib import Path

import py7zr

from typing import Optional

from paxishi_extractor.core import (
    check_and_truncate_long_filenames,
    collect_7z_files,
    decompress_7z_files,
    delete_files,
    rename_7z_suffixes,
    sanitize_filename_for_nas,
)


def _write_text(path: Path, text: str = "data") -> None:
    path.write_text(text, encoding="utf-8")


def _create_7z(archive_path: Path, files: list[Path], password: Optional[str] = None) -> None:
    with py7zr.SevenZipFile(archive_path, mode="w", password=password) as archive:
        for file_path in files:
            archive.write(file_path, arcname=file_path.name)


def test_rename_7z_suffixes_renames_when_contains_7z(tmp_path: Path) -> None:
    target = tmp_path / "movie7zpart.rar"
    _write_text(target)
    _write_text(tmp_path / "already.7z")
    _write_text(tmp_path / "notes.txt")

    stats = rename_7z_suffixes(tmp_path)

    assert not target.exists()
    assert (tmp_path / "movie7z.7z").exists()
    assert (tmp_path / "already.7z").exists()
    assert (tmp_path / "notes.txt").exists()
    assert stats.renamed == 1


def test_collect_7z_files_recurses(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    _write_text(tmp_path / "one.7z")
    _write_text(nested / "two.7z")

    files = collect_7z_files(tmp_path)

    assert {path.name for path in files} == {"one.7z", "two.7z"}


def test_sanitize_filename_for_nas_keeps_valid_name(tmp_path: Path) -> None:
    file_path = tmp_path / "valid.txt"
    _write_text(file_path)

    sanitized = sanitize_filename_for_nas(file_path.name, file_path)

    assert sanitized == "valid.txt"


def test_sanitize_filename_for_nas_removes_invalid_chars(tmp_path: Path) -> None:
    sanitized = sanitize_filename_for_nas("bad/name?.txt", tmp_path / "bad.txt")

    assert "/" not in sanitized
    assert "?" not in sanitized
    assert sanitized.endswith(".txt")


def test_check_and_truncate_long_filenames_shortens(tmp_path: Path) -> None:
    long_name = "a" * 80 + ".txt"
    file_path = tmp_path / long_name
    _write_text(file_path)

    stats = check_and_truncate_long_filenames(tmp_path)

    renamed_files = list(tmp_path.iterdir())
    assert len(renamed_files) == 1
    assert renamed_files[0].suffix == ".txt"
    assert len(renamed_files[0].stem.encode("utf-8")) <= 30
    assert stats.renamed == 1


def test_decompress_7z_files_success(tmp_path: Path) -> None:
    source = tmp_path / "data.txt"
    _write_text(source, "hello")
    archive = tmp_path / "data.7z"
    _create_7z(archive, [source])
    source.unlink()

    ok = decompress_7z_files([archive], password=None, executor=None)

    assert ok is True
    assert (tmp_path / "data.txt").exists()


def test_decompress_7z_files_wrong_password(tmp_path: Path) -> None:
    source = tmp_path / "secret.txt"
    _write_text(source, "secret")
    archive = tmp_path / "secret.7z"
    _create_7z(archive, [source], password="good")
    source.unlink()

    ok = decompress_7z_files([archive], password="bad", executor=None)

    assert ok is False


def test_delete_files_removes_files(tmp_path: Path) -> None:
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    _write_text(file_a)
    _write_text(file_b)

    stats = delete_files([file_a, file_b])

    assert not file_a.exists()
    assert not file_b.exists()
    assert stats.deleted == 2
