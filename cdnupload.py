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
# TODO: add something like --dest-help=s3 to show help/args on the Destination class
# TODO: docstrings
# TODO: tests
# TODO: python2 support
# TODO: README, LICENSE, etc

import argparse
import fnmatch
import hashlib
import logging
import mimetypes
import os
import re
import shutil
import sys
import urllib.parse


__version__ = '1.0.0'

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


def walk_files(source_root, dot_names=False, include=None, exclude=None):
    """Generate list of relative paths starting at source_root and walking the
    directory tree recursively.

    Include directories and files starting with '.' if dot_names is True
    (exclude them by default). If include is specified, only include relative
    paths that match include (per fnmatch), or one of the includes if tuple or
    list is given. If exclude is specified, exclude any relative paths that
    match exclude, or one of the excludes if tuple or list is given.
    """
    if sys.platform == 'win32' and isinstance(source_root, bytes):
        # Because os.walk() doesn't handle Unicode chars in walked paths on
        # Windows if a bytes path is specified (easy on Python 2.x with "str")
        source_root = source_root.decode(sys.getfilesystemencoding())

    if include and not isinstance(include, (tuple, list)):
        include = [include]
    if exclude and not isinstance(exclude, (tuple, list)):
        exclude = [exclude]

    for root, dirs, files in os.walk(source_root):
        if not dot_names:
            dirs[:] = [d for d in dirs if not d.startswith('.')]

        for file in files:
            if not dot_names and file.startswith('.'):
                continue
            path = os.path.relpath(os.path.join(root, file), source_root)
            if include and not any(fnmatch.fnmatch(path, i) for i in include):
                continue
            if exclude and any(fnmatch.fnmatch(path, e) for e in exclude):
                continue

            yield path


def build_key_map(source_root, hash_length=DEFAULT_HASH_LENGTH,
                  dot_names=False, include=None, exclude=None):
    keys_by_path = {}
    for rel_path in walk_files(source_root, dot_names=dot_names,
                               include=include, exclude=exclude):
        full_path = os.path.join(source_root, rel_path)
        file_hash = hash_file(full_path)
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
        # Import boto3 at runtime so it's not required to use cdnupload.py
        try:
            import boto3
        except ImportError:
            raise Exception('boto3 must be installed to upload to S3, try: pip install boto3')

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
           hash_length=DEFAULT_HASH_LENGTH, continue_on_errors=False,
           dot_names=False, include=None, exclude=None):
    source_key_map = build_key_map(
        source_root, hash_length=hash_length,
        dot_names=dot_names, include=include, exclude=exclude,
    )

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
           hash_length=DEFAULT_HASH_LENGTH, continue_on_errors=True,
           dot_names=False, include=None, exclude=None):
    source_key_map = build_key_map(
        source_root, hash_length=hash_length,
        dot_names=dot_names, include=include, exclude=exclude,
    )
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
                        help='optional Destination() keyword args, for example access-key=XYZ')
    parser.add_argument('-a', '--action', choices=['upload', 'delete'], default='upload',
                        help='action to perform, default %(default)s')
    parser.add_argument('-c', '--continue-on-errors', action='store_true',
                        help='continue after upload or delete errors (default is to stop on first error)')
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help='show what we would upload or delete instead of actually doing it')
    parser.add_argument('-f', '--force', action='store_true',
                        help='force upload even if destination file already exists')
    parser.add_argument('-i', '--include', action='append',
                        help='only include source file if its relative path matches, '
                             'for example *.png or images/* (may be specified multiple times)')
    parser.add_argument('-l', '--log-level', default='default',
                        choices=['verbose', 'default', 'quiet', 'errors', 'off'],
                        help='set logging level')
    parser.add_argument('-s', '--hash-length', type=int, default=DEFAULT_HASH_LENGTH,
                        help='number of chars of hash to use (default %(default)d)')
    parser.add_argument('-t', '--dot-names', action='store_true',
                        help='include source files and directories starting with "." (exclude by default)')
    parser.add_argument('-x', '--exclude', action='append',
                        help='exclude source file if its relative path matches, '
                             'for example *.txt or __pycache__/* (may be specified multiple times)')
    args = parser.parse_args()

    log_levels = {
        'verbose': logging.DEBUG,
        'default': logging.INFO,
        'quiet': logging.WARNING,
        'errors': logging.ERROR,
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

    try:
        destination = destination_class(args.destination, **dest_kwargs)
    except Exception as error:
        logger.error('ERROR creating %s instance: %s', destination_class.__name__, error)
        sys.exit(1)

    action_kwargs = dict(
        source_root=args.source,
        destination=destination,
        dry_run=args.dry_run,
        hash_length=args.hash_length,
        continue_on_errors=args.continue_on_errors,
        dot_names=args.dot_names,
        include=args.include,
        exclude=args.exclude,
    )
    try:
        if args.action == 'upload':
            _, _, num_errors = upload(**action_kwargs, force=args.force)
        elif args.action == 'delete':
            _, _, num_errors = delete(**action_kwargs)
        else:
            assert 'unexpected action {!r}'.format(args.action)
    except DestinationError as error:
        logger.error('ERROR with destination: %s', error)
        num_errors = 1

    sys.exit(1 if num_errors else 0)


if __name__ == '__main__':
    main()
