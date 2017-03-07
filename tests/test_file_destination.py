"""Test FileDestination class."""

from cdnupload import FileDestination


def test_file_destination(tmpdir):
    d = FileDestination(tmpdir.strpath)
    assert sorted(d.keys()) == []

    tmpdir.join('file.txt').write_binary(b'foo')
    tmpdir.join('dir').mkdir()
    tmpdir.join('dir', 'dirfile.txt').write_binary(b'bar')
#    assert sorted(d.keys()) == []
