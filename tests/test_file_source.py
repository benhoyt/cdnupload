"""Test FileSource class."""

import os
import hashlib
import sys

import pytest

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


def test_hash_file_chunk_size(tmpdir):
    class MockHasher:
        updates = []

        def update(self, chunk):
            self.updates.append(chunk)

        def hexdigest(self):
            return hashlib.sha1(b''.join(self.updates)).hexdigest()

    tmpdir.join('big').write_binary(b'x' * 65537)
    s = FileSource(tmpdir.strpath, hash_class=MockHasher)
    assert s.hash_file('big', is_text=False) == '73e6b534aafc0df0abf8bed462d387cf503cd776'
    assert MockHasher.updates == [b'x' * 65536, b'x']

    MockHasher.updates = []
    tmpdir.join('small').write_binary(b'x' * 1025)
    s = FileSource(tmpdir.strpath, hash_chunk_size=1024, hash_class=MockHasher)
    assert s.hash_file('small', is_text=False) == 'dc0849dc97d2e7d5f575b1abdc5fa96d4989165f'
    assert MockHasher.updates == [b'x' * 1024, b'x']


def test_make_key():
    s = FileSource('static')
    assert s.make_key('script.js', 'deadbeef0123456789') == 'script_deadbeef01234567.js'

    s = FileSource('static', hash_length=7)
    assert s.make_key('script.js', 'deadbeef0123456789') == 'script_deadbee.js'
    assert s.make_key('foo', 'abcdef012345') == 'foo_abcdef0'

    s = FileSource('static', hash_length=100)
    assert s.make_key('script.js', 'deadbeef0123456789') == 'script_deadbeef0123456789.js'


def test_walk_files_dot_names(tmpdir):
    tmpdir.join('.dot_dir').mkdir()
    tmpdir.join('.dot_dir', '.dot_dir_dot_file').write_binary(b'test2')
    tmpdir.join('.dot_dir', 'dot_dir_file').write_binary(b'test1')
    tmpdir.join('.dot_file').write_binary(b'test3')
    tmpdir.join('dir').mkdir()
    tmpdir.join('dir', '.dir_dot_file').write_binary(b'test5')
    tmpdir.join('dir', 'dir_file').write_binary(b'test4')
    tmpdir.join('file').write_binary(b'test6')

    s = FileSource(tmpdir.strpath)
    assert sorted(s.walk_files()) == ['dir/dir_file', 'file']

    s = FileSource(tmpdir.strpath, dot_names=True)
    assert sorted(s.walk_files()) == [
        '.dot_dir/.dot_dir_dot_file',
        '.dot_dir/dot_dir_file',
        '.dot_file',
        'dir/.dir_dot_file',
        'dir/dir_file',
        'file',
    ]


def test_walk_files_include_exclude(tmpdir):
    tmpdir.join('file.txt').write_binary(b'text')
    tmpdir.join('image1.jpg').write_binary(b'image1')
    tmpdir.join('sub').mkdir()
    tmpdir.join('sub', 'sub_file.txt').write_binary(b'text')
    tmpdir.join('sub', 'sub_image1.jpg').write_binary(b'image1')
    tmpdir.join('sub', 'subsub').mkdir()
    tmpdir.join('sub', 'subsub', 'subsub_file.txt').write_binary(b'text')
    tmpdir.join('sub', 'subsub', 'subsub_image1.jpg').write_binary(b'image1')

    s = FileSource(tmpdir.strpath)
    assert sorted(s.walk_files()) == [
        'file.txt',
        'image1.jpg',
        'sub/sub_file.txt',
        'sub/sub_image1.jpg',
        'sub/subsub/subsub_file.txt',
        'sub/subsub/subsub_image1.jpg',
    ]

    s = FileSource(tmpdir.strpath, include='*.jpg')
    assert sorted(s.walk_files()) == [
        'image1.jpg',
        'sub/sub_image1.jpg',
        'sub/subsub/subsub_image1.jpg',
    ]

    s = FileSource(tmpdir.strpath, include=['*.jpg', '*.txt'])
    assert sorted(s.walk_files()) == [
        'file.txt',
        'image1.jpg',
        'sub/sub_file.txt',
        'sub/sub_image1.jpg',
        'sub/subsub/subsub_file.txt',
        'sub/subsub/subsub_image1.jpg',
    ]

    s = FileSource(tmpdir.strpath, include='sub/sub_image1.jpg')
    assert sorted(s.walk_files()) == [
        'sub/sub_image1.jpg',
    ]

    s = FileSource(tmpdir.strpath, include=['*.jpg', '*.txt'], exclude='file.txt')
    assert sorted(s.walk_files()) == [
        'image1.jpg',
        'sub/sub_file.txt',
        'sub/sub_image1.jpg',
        'sub/subsub/subsub_file.txt',
        'sub/subsub/subsub_image1.jpg',
    ]

    s = FileSource(tmpdir.strpath, include=('*.jpg', '*.txt'), exclude=('sub/subsub/subsub_file.txt', '*.jpg'))
    assert sorted(s.walk_files()) == [
        'file.txt',
        'sub/sub_file.txt',
    ]


@pytest.mark.skipif(not hasattr(os, 'symlink'), reason='no os.symlink()')
def test_walk_files_follow_symlinks(tmpdir):
    tmpdir.join('target').mkdir()
    tmpdir.join('target', 'test.txt').write_binary(b'foo')
    tmpdir.join('walkdir').mkdir()
    tmpdir.join('walkdir', 'file').write_binary(b'bar')


    try:
        try:
            os.symlink(tmpdir.join('target').strpath, tmpdir.join('walkdir', 'link').strpath,
                       target_is_directory=True)
        except TypeError:
            # Python 2.x doesn't support the target_is_directory parameter
            os.symlink(tmpdir.join('target').strpath, tmpdir.join('walkdir', 'link').strpath)
    except NotImplementedError:
        pytest.skip('symlinks only supported on Windows Vista or later')

    s = FileSource(tmpdir.join('walkdir').strpath)
    assert sorted(s.walk_files()) == ['file']

    s = FileSource(tmpdir.join('walkdir').strpath, follow_symlinks=True)
    assert sorted(s.walk_files()) == ['file', 'link/test.txt']


def test_walk_files_errors(tmpdir):
    def check_walk_error(file_source, error_path):
        try:
            list(file_source.walk_files())
            assert False  # shouldn't get here
        except OSError as error:
            # On Python 2.x on Windows, error.filename includes '*.*'
            assert (error.filename == error_path or
                    error.filename == os.path.join(error_path, '*.*'))

    not_exists = tmpdir.join('not_exists')
    s = FileSource(not_exists.strpath)
    check_walk_error(s, not_exists.strpath)

    # Should raise an error on root path even if ignore_walk_errors is True
    s = FileSource(not_exists.strpath, ignore_walk_errors=True)
    check_walk_error(s, not_exists.strpath)

    def mock_os_walk(top, onerror=None, followlinks=False):
        yield (os.path.join(top, '.'), ['bad_dir', 'good_dir'], ['script.js'])
        if onerror:
            error = OSError()
            error.filename = 'bad_dir'
            onerror(error)
        yield (os.path.join(top, 'good_dir'), [], ['test.txt'])

    s = FileSource(tmpdir.strpath, _os_walk=mock_os_walk)
    check_walk_error(s, 'bad_dir')

    s = FileSource(tmpdir.strpath, ignore_walk_errors=True, _os_walk=mock_os_walk)
    assert sorted(s.walk_files()) == ['good_dir/test.txt', 'script.js']


def test_walk_files_unicode(tmpdir):
    tmpdir.join(u'foo\u2012.txt').write_binary(b'unifoo')
    s = FileSource(tmpdir.strpath)
    assert sorted(s.walk_files()) == [u'foo\u2012.txt']

    if not isinstance(tmpdir.strpath, bytes):
        bytes_path = bytes(tmpdir.strpath, sys.getfilesystemencoding())
    else:
        bytes_path = tmpdir.strpath
    s = FileSource(bytes_path)
    assert sorted(s.walk_files()) == [u'foo\u2012.txt']


def test_build_key_map(tmpdir):
    tmpdir.join('script.js').write_binary(b'/* test */')
    tmpdir.join('images').mkdir()
    tmpdir.join('images', 'foo1.jpg').write_binary(b'foo1')
    tmpdir.join('images', 'foo2.jpg').write_binary(b'foo2')

    s = FileSource(tmpdir.strpath)
    keys = s.build_key_map()
    assert sorted(keys) == ['images/foo1.jpg', 'images/foo2.jpg', 'script.js']
    assert keys['script.js'] == 'script_49016b58bbcc6182.js'
    assert keys['images/foo1.jpg'] == 'images/foo1_18a16d4530763ef4.jpg'
    assert keys['images/foo2.jpg'] == 'images/foo2_aaadd94977b8fbf3.jpg'


def test_build_key_map_caching(tmpdir):
    tmpdir.join('test.txt').write_binary(b'foo')

    num_walks = [0]
    def count_os_walk(*args, **kwargs):
        num_walks[0] += 1
        for root, dirs, files in os.walk(*args, **kwargs):
            yield (root, dirs, files)

    s = FileSource(tmpdir.strpath, _os_walk=count_os_walk)
    assert s.build_key_map() == {'test.txt': 'test_0beec7b5ea3f0fdb.txt'}
    assert num_walks[0] == 1
    assert s.build_key_map() == {'test.txt': 'test_0beec7b5ea3f0fdb.txt'}
    assert num_walks[0] == 1

    num_walks[0] = 0
    s = FileSource(tmpdir.strpath, cache_key_map=False, _os_walk=count_os_walk)
    assert s.build_key_map() == {'test.txt': 'test_0beec7b5ea3f0fdb.txt'}
    assert num_walks[0] == 1
    assert s.build_key_map() == {'test.txt': 'test_0beec7b5ea3f0fdb.txt'}
    assert num_walks[0] == 2
