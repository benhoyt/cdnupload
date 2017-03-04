"""Test FileSource methods."""

import os
import hashlib

import cdnupload


def test_init():
    s = cdnupload.FileSource('one')
    assert s.root == 'one'
    assert not s.dot_names
    assert s.include is None
    assert s.exclude is None
    assert not s.ignore_walk_errors
    assert not s.follow_symlinks
    assert s.hash_length == 16
    assert s.hash_chunk_size == 65536
    assert s.hash_class == hashlib.sha1
    assert s.os_walk == os.walk

    s = cdnupload.FileSource(
        'two')
    assert s.root == 'two'
    assert not s.dot_names
    assert s.include is None
    assert s.exclude is None
    assert not s.ignore_walk_errors
    assert not s.follow_symlinks
    assert s.hash_length == 16
    assert s.hash_chunk_size == 65536
    assert s.hash_class == hashlib.sha1
    assert s.os_walk == os.walk
