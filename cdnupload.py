
# TODO: exception handling
# TODO: warn about text files on Windows
# TODO: tests
# TODO: python2 support

"""
_keys_by_path = {}


def static_url(rel_path):
    return _keys_by_path[rel_path]


# put this in cdnupload.py


def init_server():
    global _keys_by_path
    _keys_by_path = build_key_map('static/')
    # OR
    _keys_by_path = load_key_map()

    def static_url(url):
    flask_env.filters['static_url'] = static_url


def save_key_map():
    with open('static_key_map.json', 'w') as f:
        json.dump(f, build_key_map('static/'))


def load_key_map():
    with open('static_key_map.json') as f:
        return json.load(f)
"""

from urllib.parse import urlparse
import argparse
import hashlib
import logging
import mimetypes
import os
import shutil

# TODO: S3Destination
# import boto3


DEFAULT_HASH_LENGTH = 16


logger = logging.getLogger('cdnupload')


def file_chunks(path, mode='rb', chunk_size=64*1024):
    """Read file at given path in chunks of given size and yield chunks."""
    with open(path, mode) as file:
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            yield chunk


def hash_file(path):
    """Read file at given path and return content hash as hex string."""
    sha1 = hashlib.sha1()
    for chunk in file_chunks(path):
        sha1.update(chunk)
    return sha1.hexdigest()


def make_key(rel_path, file_hash, hash_length=DEFAULT_HASH_LENGTH):
    """Convert relative path and file hash to key."""
    rel_file, ext = os.path.splitext(rel_path)
    key = '{}_{:.{}}{}'.format(rel_file, file_hash, hash_length, ext)
    key = key.replace('\\', '/')  # ensure \ is converted to / on Windows
    return key


def walk_files(source_root):
    # TODO: includes/excludes/.prefix
    for root, dirs, files in os.walk(source_root):
        for file in files:
            yield os.path.join(root, file)


def build_key_map(source_root, hash_length=DEFAULT_HASH_LENGTH):
    keys_by_path = {}
    for full_path in walk_files(source_root):
        file_hash = hash_file(full_path)
        rel_path = os.path.relpath(full_path, source_root)
        rel_path = rel_path.replace('\\', '/')
        key = make_key(rel_path, file_hash, hash_length=hash_length)
        keys_by_path[rel_path] = key
    return keys_by_path


class Destination(object):
    def keys(self):
        raise NotImplementedError

    def upload(self, key, source_path, content_type):
        raise NotImplementedError

    def delete(self, key):
        raise NotImplementedError


class FileDestination(Destination):
    def __init__(self, root):
        self.root = root

    def __str__(self):
        return self.root

    def keys(self):
        for root, dirs, files in os.walk(self.root):
            for file in files:
                path = os.path.join(root, file)
                key = os.path.relpath(path, self.root)
                yield key.replace('\\', '/')

    def upload(self, key, source_path, content_type):
        dest_path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True) # TODO: old Python versions?
        shutil.copyfile(source_path, dest_path)

    def delete(self, key):
        os.remove(os.path.join(self.root, key))


class S3Destination(Destination):
    def __init__(self, s3_url=None, bucket_name=None, key_prefix=None):
        if s3_url is not None:
            parsed = urlparse(s3_url)
            if parsed.scheme != 's3':
                raise ValueError('s3_url must start with s3://')
            if not parsed.netloc:
                raise ValueErrro('s3_url must include a bucket name')
            bucket_name = parsed.netloc
            key_prefix = parsed.path.lstrip('/')
        elif bucket_name is None or key_prefix is None:
            raise TypeError('you must specify either s3_url or bucket_name and key_prefix')

        self.bucket_name = bucket_name
        self.key_prefix = key_prefix

    def __str__(self):
        return 's3://{}/{}'.format(self.bucket_name, self.key_prefix)

    def keys(self):
        pass

    def upload(self, key, source_path, content_type):
        pass

    def delete(self, key):
        pass


def upload(source_root, destination, force=False, dry_run=False,
           hash_length=DEFAULT_HASH_LENGTH):
    source_key_map = build_key_map(source_root, hash_length=hash_length)
    dest_keys = set(destination.keys())

    options = []
    if force:
        options.append('forced')
    if dry_run:
        options.append('dry-run')
    logger.info('starting upload to %s%s: %d source files, %d destination keys',
                destination,
                ' (' + ', '.join(options) + ')' if options else '',
                len(source_key_map),
                len(dest_keys))

    num_scanned = 0
    num_uploaded = 0
    for rel_path, key in sorted(source_key_map.items()):
        num_scanned += 1

        if not force and key in dest_keys:
            logger.debug('already uploaded %s, skipping', key)
            continue

        if key in dest_keys:
            verb = 'would force upload' if dry_run else 'force uploading'
        else:
            verb = 'would upload' if dry_run else 'uploading'
        content_type = mimetypes.guess_type(rel_path)[0]
        logger.warning('%s %s to %s (%s)', verb, rel_path, key, content_type)
        if not dry_run:
            destination.upload(key, source_path, content_type)
        num_uploaded += 1

    logger.info('finished upload: uploaded %d, skipped %d',
                num_uploaded, len(source_paths) - num_uploaded)
    return (num_scanned, num_uploaded)


def delete(source_root, destination, dry_run=False,
           hash_length=DEFAULT_HASH_LENGTH):
    source_key_map = build_key_map(source_root, hash_length=hash_length)
    source_keys = set(source_key_map.values())
    dest_keys = set(destination.keys())

    options = []
    if dry_run:
        options.append('dry-run')
    logger.info('starting delete from %s%s: %d source files, %d destination keys',
                destination,
                ' (' + ', '.join(options) + ')' if options else '',
                len(source_keys),
                len(dest_keys))

    num_scanned = 0
    num_deleted = 0
    for key in dest_keys:
        num_scanned += 1

        if key in source_keys:
            logging.debug('still using %s, skipping', key)
            continue

        verb = 'would delete' if dry_run else 'deleting'
        logger.warning('%s %s', verb, key)
        if not dry_run:
            destination.delete(key)
        num_deleted += 1

    logger.info('finished delete: deleted %d', num_deleted)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source',
                        help='source directory to upload from')
    parser.add_argument('destination',
                        help='destination directory (or s3://bucket/path) to upload to')
    parser.add_argument('-a', '--action', choices=['upload', 'delete'], default='upload',
                        help='action to perform, default %(default)r')
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help='show what we would upload or delete instead of actually doing it')
    parser.add_argument('-f', '--force', action='store_true',
                        help='force upload even if destination file already exists')
    parser.add_argument('-l', '--hash-length', type=int, default=DEFAULT_HASH_LENGTH,
                        help='number of chars of hash to use (default %(default)d)')
    parser.add_argument('-o', '--log-level',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO',
                        help='set logging level (DEBUG=verbose, INFO=default, WARNING=quiet, ERROR=errors, CRITICAL=off)')
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level, format='%(message)s')

    if args.destination.startswith('s3://'):
        destination = S3Destination(s3_url=args.destination)
    else:
        destination = FileDestination(args.destination)

    if args.action == 'upload':
        upload(args.source, destination, force=args.force,
               dry_run=args.dry_run, hash_length=args.hash_length)
    elif args.action == 'delete':
        delete(args.source, destination, dry_run=args.dry_run,
               hash_length=args.hash_length)
    else:
        assert 'unexpected action {!r}'.format(args.action)


if __name__ == '__main__':
    main()
