"""Test S3Destination class.

This is very much white-box testing, and not testing the actual upload to S3,
but it'll do for now.
"""

import pytest

from cdnupload import S3Destination, FileSource


class MockBoto3:
    def __init__(self, bucket=None, prefix=None, keys=None):
        self._bucket = bucket
        self._prefix = prefix
        self._keys = keys

    def client(self, name, **client_args):
        assert name == 's3'
        self._s3 = MockS3Client(self._bucket, self._prefix, self._keys, **client_args)
        return self._s3


class MockPaginator:
    def __init__(self, bucket, prefix, keys):
        self._bucket = bucket
        self._prefix = prefix
        self._keys = keys

    def paginate(self, Bucket, Prefix=None, PaginationConfig=None):
        assert Bucket == self._bucket
        assert Prefix == self._prefix
        assert PaginationConfig == {'PageSize': 1000}
        yield {'Contents': [{'Key': k} for k in self._keys]}


class MockS3Client:
    def __init__(self, bucket, prefix, keys, **client_args):
        self._bucket = bucket
        self._prefix = prefix
        self._keys = keys
        self._args = client_args
        self._uploads = []
        self._deletions = []

    def get_paginator(self, name):
        assert name == 'list_objects_v2'
        return MockPaginator(self._bucket, self._prefix, self._keys)

    def upload_fileobj(self, file, bucket, key, ExtraArgs=None):
        self._uploads.append((bucket, key, file.read(), ExtraArgs))

    def delete_object(self, Bucket, Key):
        self._deletions.append((Bucket, Key))


def test_str():
    d = S3Destination('s3://bucket/prefix', _boto3=MockBoto3())
    assert str(d) == 's3://bucket/prefix/'

    d = S3Destination('s3://bucket2/prefix2/', _boto3=MockBoto3())
    assert str(d) == 's3://bucket2/prefix2/'


def test_init():
    d = S3Destination('s3://test-bucket/key/prefix', _boto3=MockBoto3())
    assert d.bucket_name == 'test-bucket'
    assert d.key_prefix == 'key/prefix/'
    assert d.upload_args == {
        'ACL': 'public-read',
        'CacheControl': 'public, max-age=31536000',
    }
    assert d.s3_client._args['region_name'] is None
    assert d.s3_client._args['aws_access_key_id'] is None
    assert d.s3_client._args['aws_secret_access_key'] is None

    d = S3Destination('s3://test-bucket/key/prefix', max_age=60, _boto3=MockBoto3())
    assert d.upload_args['CacheControl'] == 'public, max-age=60'

    d = S3Destination('s3://test-bucket/key/prefix', cache_control='foo, bar', _boto3=MockBoto3())
    assert d.upload_args['CacheControl'] == 'foo, bar'

    with pytest.raises(ValueError):
        d = S3Destination('http://example.com', _boto3=MockBoto3())
    with pytest.raises(ValueError):
        d = S3Destination('s3:path', _boto3=MockBoto3())
    with pytest.raises(ValueError):
        d = S3Destination('s3:///path', _boto3=MockBoto3())

    d = S3Destination(
        's3://bucket/prefix',
        upload_args={'ContentDisposition': 'attachment', 'ACL': 'foo', 'CacheControl': 'bar'},
        _boto3=MockBoto3(),
    )
    assert d.upload_args == {
        'ACL': 'foo',
        'CacheControl': 'bar',
        'ContentDisposition': 'attachment',
    }

    d = S3Destination(
        's3://bucket/prefix',
        region_name='REGION',
        access_key='KEY',
        secret_key='SECRET',
        _boto3=MockBoto3(),
    )
    assert d.s3_client._args['region_name'] == 'REGION'
    assert d.s3_client._args['aws_access_key_id'] == 'KEY'
    assert d.s3_client._args['aws_secret_access_key'] == 'SECRET'


def test_keys():
    keys = ['file.txt', 'images/', 'images/bar.jpg', 'images/foo.jpg']
    mock_boto3 = MockBoto3(bucket='buck', prefix='pref/', keys=keys)
    d = S3Destination('s3://buck/pref', _boto3=mock_boto3)
    assert sorted(d.walk_keys()) == ['file.txt', 'images/bar.jpg', 'images/foo.jpg']


def test_upload(tmpdir):
    tmpdir.join('test.txt').write_binary(b'foo')
    tmpdir.join('image.jpg').write_binary(b'bar')
    s = FileSource(tmpdir.strpath)

    mock_boto3 = MockBoto3()
    d = S3Destination('s3://bucket/prefix', max_age=60, _boto3=mock_boto3)
    d.upload('test_1234.txt', s, 'test.txt')
    mock_boto3._s3._uploads = [
        ('bucket', 'prefix/test_1234.txt', b'foo',
            {'ContentType': 'text/plain'})
    ]

    mock_boto3 = MockBoto3()
    d = S3Destination('s3://bucket/prefix', max_age=60,
                      upload_args={'Foo': 'Bar'}, _boto3=mock_boto3)
    d.upload('image_4321.txt', s, 'image.jpg')
    mock_boto3._s3._uploads = [
        ('bucket', 'prefix/image_4321.txt', b'foo',
            {'Foo': 'Bar', 'ContentType': 'image/jpeg'})
    ]


def test_delete():
    mock_boto3 = MockBoto3()
    d = S3Destination('s3://bucket/prefix', max_age=60, _boto3=mock_boto3)
    d.delete('foo')
    d.delete('bar')
    assert mock_boto3._s3._deletions == [
        ('bucket', 'prefix/foo'),
        ('bucket', 'prefix/bar'),
    ]
