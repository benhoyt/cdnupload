"""Test delete() function."""

import os

import pytest

from cdnupload import (SourceError, DestinationError, DeleteAllKeysError,
                       FileSource, FileDestination, delete, upload)


def list_files(top):
    lst = []
    for root, dirs, files in os.walk(top):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, top)
            lst.append(rel_path.replace('\\', '/'))
    lst.sort()
    return lst


def test_delete(tmpdir):
    tmpdir.join('src').mkdir()
    tmpdir.join('src', 'file.txt').write_binary(b'file.txt')
    tmpdir.join('src', 'images').mkdir()
    tmpdir.join('src', 'images', '1.jpg').write_binary(b'1.jpg')
    tmpdir.join('src', 'images', '2.jpg').write_binary(b'2.jpg')

    tmpdir.join('dest').mkdir()

    source_key_map = {
        'file.txt': 'file_5436437fa01a7d3e.txt',
        'images/1.jpg': 'images/1_accf102caaa970ce.jpg',
        'images/2.jpg': 'images/2_08fda0244b5397e0.jpg',
    }
    destination_keys = set(source_key_map.values())

    class CountingDestination(FileDestination):
        def delete(self, key):
            self._deletes += 1
            return FileDestination.delete(self, key)

    s = tmpdir.join('src').strpath
    d = CountingDestination(tmpdir.join('dest').strpath)
    d._deletes = 0

    result = upload(s, d)
    assert (result.num_scanned, result.num_processed, result.num_errors) == (3, 3, 0)
    assert result.source_key_map == source_key_map
    assert result.destination_keys == set()

    result = delete(s, d)
    assert (result.num_scanned, result.num_processed, result.num_errors) == (3, 0, 0)
    assert list_files(tmpdir.join('dest').strpath) == sorted(destination_keys)
    assert result.source_key_map == source_key_map
    assert result.destination_keys == destination_keys

    tmpdir.join('src', 'file.txt').remove()
    del source_key_map['file.txt']

    result = delete(s, d, dry_run=True)
    assert d._deletes == 0
    assert (result.num_scanned, result.num_processed, result.num_errors) == (3, 1, 0)
    assert list_files(tmpdir.join('dest').strpath) == sorted(destination_keys)
    assert result.source_key_map == source_key_map
    assert result.destination_keys == destination_keys

    result = delete(s, d)
    assert d._deletes == 1
    assert (result.num_scanned, result.num_processed, result.num_errors) == (3, 1, 0)
    assert list_files(tmpdir.join('dest').strpath) == [
        'images/1_accf102caaa970ce.jpg',
        'images/2_08fda0244b5397e0.jpg',
    ]
    assert result.source_key_map == source_key_map
    assert result.destination_keys == destination_keys

    destination_keys.remove('file_5436437fa01a7d3e.txt')
    tmpdir.join('src', 'images', '1.jpg').remove()
    tmpdir.join('src', 'images', '2.jpg').remove()
    source_key_map.clear()

    with pytest.raises(DeleteAllKeysError):
        delete(s, d)
    assert d._deletes == 1

    result = delete(s, d, force=True)
    assert d._deletes == 3
    assert (result.num_scanned, result.num_processed, result.num_errors) == (2, 2, 0)
    assert list_files(tmpdir.join('dest').strpath) == []
    assert result.source_key_map == source_key_map
    assert result.destination_keys == destination_keys


def test_delete_errors(tmpdir):
    tmpdir.join('src').mkdir()
    tmpdir.join('src', 'file1.txt').write_binary(b'file.txt')
    tmpdir.join('src', 'file2.txt').write_binary(b'file.txt')
    tmpdir.join('src', 'file3.txt').write_binary(b'file.txt')

    class DeleteErrorDestination(FileDestination):
        def delete(self, key):
            if key == 'file1_5436437fa01a7d3e.txt':
                raise Exception('error')
            else:
                return FileDestination.delete(self, key)

    s = FileSource(tmpdir.join('src').strpath, cache_key_map=False)
    dd = DeleteErrorDestination(tmpdir.join('dest').strpath)
    upload(s, dd)
    tmpdir.join('src', 'file1.txt').remove()
    tmpdir.join('src', 'file2.txt').remove()

    with pytest.raises(DestinationError):
        delete(s, dd)
    assert list_files(tmpdir.join('dest').strpath) == [
        'file1_5436437fa01a7d3e.txt',
        'file2_5436437fa01a7d3e.txt',
        'file3_5436437fa01a7d3e.txt',
    ]

    result = delete(s, dd, continue_on_errors=True)
    assert (result.num_scanned, result.num_processed, result.num_errors) == (3, 1, 1)
    assert list_files(tmpdir.join('dest').strpath) == [
        'file1_5436437fa01a7d3e.txt',
        'file3_5436437fa01a7d3e.txt',
    ]

    class ErrorKeysDestination(FileDestination):
        def walk_keys(self):
            raise Exception('error')

    dk = ErrorKeysDestination(tmpdir.join('dest').strpath)
    with pytest.raises(DestinationError):
        delete(s, dk)
    with pytest.raises(DestinationError):
        delete(s, dk, continue_on_errors=True)

    class ErrorKeyMapSource(FileSource):
        def build_key_map(self):
            raise Exception('error')

    sk = ErrorKeyMapSource(tmpdir.join('src').strpath)
    with pytest.raises(SourceError):
        delete(sk, dd)
    with pytest.raises(SourceError):
        delete(sk, dd, continue_on_errors=True)


def test_str_destination(tmpdir):
    tmpdir.join('src').mkdir()
    tmpdir.join('src', 'file.txt').write_binary(b'file.txt')

    s = tmpdir.join('src').strpath
    d = tmpdir.join('dest').strpath
    result = upload(s, d)
    assert result.num_processed == 1

    result = delete(s, d)
    assert result.num_processed == 0
