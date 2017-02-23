"""Upload static files to directory or CDN, using content-based hash for versioning.

Example usage:

_keys_by_path = {}

def init_server():
    global _keys_by_path
    _keys_by_path = build_key_map('static/')
    # OR
    _keys_by_path = load_key_map()

    def static_url(rel_path):
        return settings.static_prefix + _keys_by_path[rel_path]
    flask_env.filters['static_url'] = static_url


def save_key_map():
    with open('static_key_map.json', 'w') as f:
        json.dump(f, build_key_map('static/'), sort_keys=True, indent=4)


def load_key_map():
    with open('static_key_map.json') as f:
        return json.load(f)
"""

# TODO: handle text files (or warn on Windows and git or svn auto CRLF mode)
# TODO: includes/excludes/.prefix
# TODO: docstrings
# TODO: tests
# TODO: python2 support

import argparse
import hashlib
import logging
import mimetypes
import os
import re
import shutil
import sys
import urllib.parse


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


class DestinationError(Exception):
    def __init__(self, error, key=None):
        self.error = error
        self.key = key

    def __str__(self):
        return str(self.error)

    __repr__ = __str__


class Destination(object):
    def keys(self):
        raise NotImplementedError

    def upload(self, key, source_path):
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

    def upload(self, key, source_path):
        dest_path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copyfile(source_path, dest_path)

    def delete(self, key):
        os.remove(os.path.join(self.root, key))


class S3Destination(Destination):
    def __init__(self, s3_url):
        parsed = urllib.parse.urlparse(s3_url)
        if parsed.scheme != 's3':
            raise ValueError('s3_url must start with s3://')
        if not parsed.netloc:
            raise ValueErrro('s3_url must include a bucket name')
        self.bucket_name = parsed.netloc
        self.key_prefix = parsed.path.lstrip('/')  # TODO: should we ensure trailing slash?

    def __str__(self):
        return 's3://{}/{}'.format(self.bucket_name, self.key_prefix)

    def keys(self):
        return []
        # TODO

    def upload(self, key, source_path):
        content_type = mimetypes.guess_type(source_path)[0]
        # TODO

    def delete(self, key):
        pass
        # TODO


def upload(source_root, destination, force=False, dry_run=False,
           hash_length=DEFAULT_HASH_LENGTH, continue_on_errors=False):
    source_key_map = build_key_map(source_root, hash_length=hash_length)

    try:
        dest_keys = set(destination.keys())
    except Exception as error:
        raise DestinationError(error)

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
    num_errors = 0
    for rel_path, key in sorted(source_key_map.items()):
        num_scanned += 1

        if not force and key in dest_keys:
            logger.debug('already uploaded %s, skipping', key)
            continue

        if key in dest_keys:
            verb = 'would force upload' if dry_run else 'force uploading'
        else:
            verb = 'would upload' if dry_run else 'uploading'
        logger.warning('%s %s to %s', verb, rel_path, key)
        if not dry_run:
            source_path = os.path.join(source_root, rel_path)
            try:
                destination.upload(key, source_path)
                num_uploaded += 1
            except Exception as error:
                if not continue_on_errors:
                    raise DestinationError(error, key=key)
                logger.error('ERROR uploading to %s: %s', key, error)
                num_errors += 1
        else:
            num_uploaded += 1

    logger.info('finished upload: uploaded %d, skipped %d, errors with %d',
                num_uploaded, len(source_key_map) - num_uploaded, num_errors)
    return (num_scanned, num_uploaded, num_errors)


def delete(source_root, destination, dry_run=False,
           hash_length=DEFAULT_HASH_LENGTH, continue_on_errors=True):
    source_key_map = build_key_map(source_root, hash_length=hash_length)
    source_keys = set(source_key_map.values())

    try:
        dest_keys = set(destination.keys())
    except Exception as error:
        raise DestinationError(error)

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
    num_errors = 0
    for key in dest_keys:
        num_scanned += 1

        if key in source_keys:
            logger.debug('still using %s, skipping', key)
            continue

        verb = 'would delete' if dry_run else 'deleting'
        logger.warning('%s %s', verb, key)
        if not dry_run:
            try:
                destination.delete(key)
                num_deleted += 1
            except Exception as error:
                if not continue_on_errors:
                    raise DestinationError(error, key=key)
                logger.error('ERROR deleting %s: %s', key, error)
                num_errors += 1
        else:
            num_deleted += 1

    logger.info('finished delete: deleted %d, errors with %d',
                num_deleted, num_errors)
    return (num_scanned, num_deleted, num_errors)


def main():
    description = (
        'Upload static files from given source directory to destination directory or '
        'S3 bucket, with content-based hash in filenames for versioning.'
    )

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('source',
                        help='source directory')
    parser.add_argument('destination',
                        help='destination directory (or s3://bucket/path)')
    parser.add_argument('dest_args', nargs='*',
                        help='Destination() class args, for example access-key=XYZ')
    parser.add_argument('-a', '--action', choices=['upload', 'delete'], default='upload',
                        help='action to perform, default %(default)r')
    parser.add_argument('-c', '--continue-on-errors', action='store_true',
                        help='continue after destination errors (default is to stop on first error)')
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help='show what we would upload or delete instead of actually doing it')
    parser.add_argument('-f', '--force', action='store_true',
                        help='force upload even if destination file already exists')
    parser.add_argument('-l', '--log-level', default='default',
                        choices=['verbose', 'default', 'quiet', 'errors-only', 'off'],
                        help='set logging level')
    parser.add_argument('-s', '--hash-length', type=int, default=DEFAULT_HASH_LENGTH,
                        help='number of chars of hash to use (default %(default)d)')
    args = parser.parse_args()

    log_levels = {
        'verbose': logging.DEBUG,
        'default': logging.INFO,
        'quiet': logging.WARNING,
        'errors-only': logging.ERROR,
        'off': logging.CRITICAL,
    }
    logging.basicConfig(level=log_levels[args.log_level], format='%(message)s')

    dest_kwargs = {}
    for arg in args.dest_args:
        name, sep, value = arg.partition('=')
        if not sep:
            value = True
        name = name.replace('-', '_')
        dest_kwargs[name] = value

    match = re.match(r'(\w+):', args.destination)
    if match:
        scheme = match.group(1)
        if scheme == 's3':
            destination_class = S3Destination
        else:
            module_name = 'cdnupload_' + scheme
            try:
                module = __import__(module_name)
            except ImportError as error:
                parser.error("can't import handler for scheme {!r}: {}".format(
                        scheme, error))
            if not hasattr(module, 'Destination'):
                parser.error('{} module has no Destination class'.format(module_name))
            destination_class = getattr(module, 'Destination')
    else:
        destination_class = FileDestination
    destination = destination_class(args.destination, **dest_kwargs)

    try:
        if args.action == 'upload':
            _, _, num_errors = upload(
                args.source,
                destination,
                force=args.force,
                dry_run=args.dry_run,
                hash_length=args.hash_length,
                continue_on_errors=args.continue_on_errors,
            )
        elif args.action == 'delete':
            _, _, num_errors = delete(
                args.source,
                destination,
                dry_run=args.dry_run,
                hash_length=args.hash_length,
                continue_on_errors=args.continue_on_errors,
            )
        else:
            assert 'unexpected action {!r}'.format(args.action)
    except DestinationError as error:
        logger.error('ERROR with destination: %s', error)
        num_errors = 1

    sys.exit(1 if num_errors else 0)


if __name__ == '__main__':
    main()
