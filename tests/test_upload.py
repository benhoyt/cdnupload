"""Test upload() function."""

import os

import pytest

from cdnupload import FileSource, DestinationError, FileDestination, upload


def list_files(top):
    lst = []
    for root, dirs, files in os.walk(top):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, top)
            lst.append(rel_path.replace('\\', '/'))
    lst.sort()
    return lst


def test_upload(tmpdir):
    tmpdir.join('src').mkdir()
    tmpdir.join('src', 'file.txt').write_binary(b'file.txt')
    tmpdir.join('src', 'images').mkdir()
    tmpdir.join('src', 'images/1.jpg').write_binary(b'1.jpg')
    tmpdir.join('src', 'images/2.jpg').write_binary(b'2.jpg')

    tmpdir.join('dest').mkdir()

    dest_keys = [
        'file_5436437fa01a7d3e.txt',
        'images/1_accf102caaa970ce.jpg',
        'images/2_08fda0244b5397e0.jpg',
    ]

    s = FileSource(tmpdir.join('src').strpath)
    d = FileDestination(tmpdir.join('dest').strpath)

    result = upload(s, d, dry_run=True)
    assert result == (3, 3, 0)
    assert list_files(tmpdir.join('dest').strpath) == []

    result = upload(s, d)
    assert result == (3, 3, 0)
    assert list_files(tmpdir.join('dest').strpath) == dest_keys

    result = upload(s, d)
    assert result == (3, 0, 0)
    assert list_files(tmpdir.join('dest').strpath) == dest_keys

    result = upload(s, d, force=True)
    assert result == (3, 3, 0)
    assert list_files(tmpdir.join('dest').strpath) == dest_keys


def test_upload_errors(tmpdir):
    tmpdir.join('src').mkdir()
    tmpdir.join('src', 'file1.txt').write_binary(b'file.txt')
    tmpdir.join('src', 'file2.txt').write_binary(b'file.txt')

    class ErroringDestination(FileDestination):
        def upload(self, key, source, rel_path):
            if rel_path == 'file1.txt':
                raise DestinationError('error', Exception('exception'), key=key)
            else:
                return FileDestination.upload(self, key, source, rel_path)

    s = FileSource(tmpdir.join('src').strpath)
    d = ErroringDestination(tmpdir.join('dest').strpath)
    with pytest.raises(DestinationError):
        upload(s, d)
    assert list_files(tmpdir.join('dest').strpath) == []

    result = upload(s, d, continue_on_errors=True)
    assert result == (2, 1, 1)
    assert list_files(tmpdir.join('dest').strpath) == [
        'file2_5436437fa01a7d3e.txt',
    ]
