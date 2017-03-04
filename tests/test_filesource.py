"""Test FileSource methods."""

import os
import hashlib

from cdnupload import FileSource


def test_init():
    s = FileSource('foo')
    assert s.root == 'foo'
    assert not s.dot_names
    assert s.include is None
    assert s.exclude is None
    assert not s.ignore_walk_errors
    assert not s.follow_symlinks
    assert s.hash_length == 16
    assert s.hash_chunk_size == 65536
    assert s.hash_class == hashlib.sha1
    assert s.os_walk == os.walk

    s = FileSource('bar', include='static/*', exclude='*.pyc')
    assert s.root == 'bar'
    assert s.include == ['static/*']
    assert s.exclude == ['*.pyc']

    s = FileSource('baz', include=['static/*', 'buzz/*'], exclude=('*.pyc', '*.txt'))
    assert s.root == 'baz'
    assert s.include == ['static/*', 'buzz/*']
    assert s.exclude == ('*.pyc', '*.txt')


def test_str():
    s = FileSource('project/static')
    assert str(s) == 'project/static'


def test_open(tmpdir):
    tmpdir.join('script.js').write_binary(b'/* test */\r\nvar x = 0;')
    s = FileSource(tmpdir.strpath)
    with s.open('script.js') as f:
        contents = f.read()
    assert contents == b'/* test */\r\nvar x = 0;'


def test_hash_file(tmpdir):
    tmpdir.join('test1.txt').write_binary(b'one\r\ntwo')
    s = FileSource(tmpdir.strpath)
    assert s.hash_file('test1.txt') == 'd9822126cf6ba45822e1af99c4301244d36b1d58'
    assert s.hash_file('test1.txt', is_text=False) == 'd21fd97bafd12ccb1cd8630bf209d408ab5c4d0e'
    assert s.hash_file('test1.txt', is_text=True) == 'd9822126cf6ba45822e1af99c4301244d36b1d58'

    tmpdir.join('test2.txt').write_binary(b'binary\r\ntwo\x00')
    assert s.hash_file('test2.txt') == '2a1724c5041e12273d7f4f9be536453b04d583ef'
    assert s.hash_file('test2.txt', is_text=False) == '2a1724c5041e12273d7f4f9be536453b04d583ef'
    assert s.hash_file('test2.txt', is_text=True) == '214b18e42ccfcf6fdaca05907de3a719796c03ae'

    tmpdir.join('test3.txt').write_binary(b'\r\n' + b'x' * 7998 + b'\x00')
    assert s.hash_file('test3.txt') == 'fa3f020d7404d8bfb8c47c49375f56819406f6f2'
    assert s.hash_file('test3.txt', is_text=False) == '358de10e5733ce19e050bd23e426f2a5c107268a'
    assert s.hash_file('test3.txt', is_text=True) == 'fa3f020d7404d8bfb8c47c49375f56819406f6f2'

    s = FileSource(tmpdir.strpath, hash_class=hashlib.md5)
    assert s.hash_file('test1.txt') == '76bb1822205fc52742565357a1027fec'
    assert s.hash_file('test1.txt', is_text=False) == '9d12a9835c4f0ba19f28510b3512b73b'
    assert s.hash_file('test1.txt', is_text=True) == '76bb1822205fc52742565357a1027fec'


def test_make_key():
    s = FileSource('static')
    assert s.make_key('script.js', 'deadbeef0123456789') == 'script_deadbeef01234567.js'

    s = FileSource('static', hash_length=7)
    assert s.make_key('script.js', 'deadbeef0123456789') == 'script_deadbee.js'
    assert s.make_key('foo', 'abcdef012345') == 'foo_abcdef0'


def test_walk_files():
    pass


def test_build_key_map():
    pass

