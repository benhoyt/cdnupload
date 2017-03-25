"""Test FileDestination class."""

from cdnupload import FileDestination, FileSource


def test_str():
    d = FileDestination('foo/bar')
    assert str(d) == 'foo/bar'


def test_file_operations(tmpdir):
    tmpdir.join('src').mkdir()
    tmpdir.join('src', 'file.txt').write_binary(b'foo')
    tmpdir.join('src', 'subdir').mkdir()
    tmpdir.join('src', 'subdir', 'subfile.txt').write_binary(b'foo')

    s = FileSource(tmpdir.join('src').strpath)
    keys = s.build_key_map()
    assert keys == {
        'file.txt': 'file_0beec7b5ea3f0fdb.txt',
        'subdir/subfile.txt': 'subdir/subfile_0beec7b5ea3f0fdb.txt',
    }

    d = FileDestination(tmpdir.join('dest').strpath)
    assert sorted(d.walk_keys()) == []

    d.upload(keys['file.txt'], s, 'file.txt')
    assert sorted(d.walk_keys()) == ['file_0beec7b5ea3f0fdb.txt']

    d.upload(keys['subdir/subfile.txt'], s, 'subdir/subfile.txt')
    assert sorted(d.walk_keys()) == [
        'file_0beec7b5ea3f0fdb.txt',
        'subdir/subfile_0beec7b5ea3f0fdb.txt',
    ]

    d.delete(keys['file.txt'])
    assert sorted(d.walk_keys()) == ['subdir/subfile_0beec7b5ea3f0fdb.txt']
