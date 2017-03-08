"""Test upload() function."""

import os

import pytest

from cdnupload import SourceError, DestinationError, FileSource, FileDestination, upload


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

    class CountingDestination(FileDestination):
        def upload(self, key, source, rel_path):
            self._uploads += 1
            return FileDestination.upload(self, key, source, rel_path)

    s = tmpdir.join('src').strpath
    d = CountingDestination(tmpdir.join('dest').strpath)
    d._uploads = 0

    result = upload(s, d, dry_run=True)
    assert result == (3, 3, 0)
    assert d._uploads == 0
    assert list_files(tmpdir.join('dest').strpath) == []

    result = upload(s, d)
    assert result == (3, 3, 0)
    assert d._uploads == 3
    assert list_files(tmpdir.join('dest').strpath) == dest_keys

    result = upload(s, d)
    assert result == (3, 0, 0)
    assert d._uploads == 3
    assert list_files(tmpdir.join('dest').strpath) == dest_keys

    result = upload(s, d, force=True)
    assert result == (3, 3, 0)
    assert d._uploads == 6
    assert list_files(tmpdir.join('dest').strpath) == dest_keys


def test_upload_errors(tmpdir):
    tmpdir.join('src').mkdir()
    tmpdir.join('src', 'file1.txt').write_binary(b'file.txt')
    tmpdir.join('src', 'file2.txt').write_binary(b'file.txt')

    class ErrorUploadDestination(FileDestination):
        def upload(self, key, source, rel_path):
            if rel_path == 'file1.txt':
                raise Exception('error')
            else:
                return FileDestination.upload(self, key, source, rel_path)

    s = FileSource(tmpdir.join('src').strpath)
    du = ErrorUploadDestination(tmpdir.join('dest').strpath)
    with pytest.raises(DestinationError):
        upload(s, du)
    assert list_files(tmpdir.join('dest').strpath) == []

    result = upload(s, du, continue_on_errors=True)
    assert result == (2, 1, 1)
    assert list_files(tmpdir.join('dest').strpath) == [
        'file2_5436437fa01a7d3e.txt',
    ]

    class ErrorKeysDestination(FileDestination):
        def keys(self):
            raise Exception('error')

    dk = ErrorKeysDestination(tmpdir.join('dest').strpath)
    with pytest.raises(DestinationError):
        upload(s, dk)
    with pytest.raises(DestinationError):
        upload(s, dk, continue_on_errors=True)

    class ErrorKeyMapSource(FileSource):
        def build_key_map(self):
            raise Exception('error')

    sk = ErrorKeyMapSource(tmpdir.join('src').strpath)
    with pytest.raises(SourceError):
        upload(sk, du)
    with pytest.raises(SourceError):
        upload(sk, du, continue_on_errors=True)
