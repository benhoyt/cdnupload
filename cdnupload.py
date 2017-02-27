"""Upload static files to directory or CDN, using content-based hashing.

Run "python cdnupload.py -h" for command line help. See README.rst for
documentation, and LICENSE.txt for license information. Visit the project's
website or GitHub repo for more information:

https://cdnupload.com/
https://github.com/benhoyt/cdnupload

TODO:
* s3
  - better auth error handling: ERROR with destination: An error occurred (AccessDenied) when calling the ListObjects operation: Access Denied
* handle text files (or warn on Windows and git or svn auto CRLF mode)
* consider adding 'blob {size}\x00' to hash like git
* tests
  - test handling of unicode filenames (round trip)
* python2 support
* README, LICENSE, etc
"""

from __future__ import print_function

import argparse
import fnmatch
import hashlib
import logging
import mimetypes
import os
import re
import shutil
import sys
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse


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
    """Walk directory tree starting at source_root and build a dict that maps
    relative path to key including content-based hash (of given length). The
    dot_names, include, and exclude parameters are handled as per the
    walk_files() function.

    The relative paths are "canonical", meaning \ is converted to / on
    Windows, so that users of the mapping can always look up keys using
    "dir/file.ext" style paths, regardless of operating system.
    """
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
    """Raised when an error occurs accessing the destination (usually
    uploading or deleting), so that callers can catch a more specific error
    than just Exception. Where relevant, includes the destination key in
    question.
    """
    def __init__(self, message, exception, key=None):
        self.message = message
        self.exception = exception
        self.key = key

    def __str__(self):
        return '{}: {}'.format(self.message, self.exception)

    __repr__ = __str__


class Destination(object):
    """Subclass this abstract base class to implement a destination uploader,
    for example uploading to Amazon S3, or to Google Cloud Storage.
    """
    def __init__(self, destination, **kwargs):
        """Initialize instance with given destination "URL", for example
        /www/static or s3://bucket/key/prefix. Format of destination arg and
        names of kwargs depend on the subclass.
        """
        raise NotImplementedError

    def __str__(self):
        """Return a human-readable string describing this destination, for
        example 's3://bucket/key/prefix/'.
        """
        raise NotImplementedError

    def keys(self):
        """Yield list of keys currently present on the destination"""
        raise NotImplementedError

    def upload(self, key, source_path):
        """Upload a single file from given source_path to destination at "key"."""
        raise NotImplementedError

    def delete(self, key):
        """Delete a single file on the destination at "key"."""
        raise NotImplementedError


class FileDestination(Destination):
    """Copies files to a destination directory.

    required argument ("destinaton" command line parameter):
      root           root of destination directory to copy to
    """
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
    """Uploads files to an Amazon S3 bucket using the boto3 library.

    required argument ("destinaton" command line parameter):
      s3_url         S3 bucket and key prefix in s3://bucket/key/prefix form
                     (trailing slash is added to key prefix if not present)

    optional arguments:
      access_key     AWS access key (if not specified, uses credentials in
                     boto3 environment variables or in ~/.aws/credentials)
      secret_key     AWS secret key
      max_age        max-age value for Cache-Control header, in seconds
      cache_control  full Cache-Control header (overrides max_age)
      acl            S3 canned ACL (access control list)
      region_name    AWS region name of S3 bucket   # TODO: usually not required?
      client_args    dict of additional keyword args for boto3 client setup:
                     boto3.client('s3', ..., **client_args)
      upload_args    dict of additional keyword args (ExtraArgs) for
                     client.upload_file() call
    """
    def __init__(self, s3_url, access_key=None, secret_key=None,
                 max_age=365*24*60*60, cache_control='public, max-age={max_age}',
                 acl='public-read', region_name=None, client_args=None,
                 upload_args=None):

        parsed = urlparse(s3_url)
        if parsed.scheme != 's3':
            raise ValueError('s3_url must start with s3://')
        if not parsed.netloc:
            raise ValueError('s3_url must include a bucket name')
        self.bucket_name = parsed.netloc
        self.key_prefix = parsed.path.lstrip('/')
        if self.key_prefix and not self.key_prefix.endswith('/'):
            self.key_prefix += '/'

        self.upload_args = upload_args or {}

        if acl and 'ACL' not in self.upload_args:
            self.upload_args['ACL'] = acl

        if cache_control and 'CacheControl' not in self.upload_args:
            try:
                max_age = int(max_age)
            except (ValueError, TypeError):
                raise TypeError('max_age must be an integer number of seconds, '
                                'not {!r}'.format(max_age))
            cache_control = cache_control.format(max_age=max_age)
            self.upload_args['CacheControl'] = cache_control

        # Import boto3 at runtime so it's not required to use cdnupload.py
        try:
            import boto3
        except ImportError:
            raise Exception('boto3 must be installed to upload to S3, try: '
                            'pip install boto3')

        self.s3_client = boto3.client(
            's3',
            region_name=region_name,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            **(client_args or {}),
        )

    def __str__(self):
        return 's3://{}/{}'.format(self.bucket_name, self.key_prefix)

    def keys(self):
        # TODO: check error handling, test with multiple pages (>1000 keys?)
        paginator = self.s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(
            Bucket=self.bucket_name,
            Delimiter='/',
            Prefix=self.key_prefix,
            PaginationConfig={'PageSize': 1000},
        )
        for response in pages:
            for obj in response['Contents']:
                yield obj['Key']

    def upload(self, key, source_path):
        # TODO: check error handling
        content_type = mimetypes.guess_type(source_path)[0]
        key = self.key_prefix + key

        extra_args = self.upload_args.copy()
        if content_type:
            extra_args['ContentType'] = content_type

        self.s3_client.upload_file(source_path, self.bucket_name, key,
                                   ExtraArgs=extra_args)

    def delete(self, key):
        # TODO: check error handling
        key = self.key_prefix + key
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)


def upload(source_root, destination, force=False, dry_run=False,
           hash_length=DEFAULT_HASH_LENGTH, continue_on_errors=False,
           dot_names=False, include=None, exclude=None):
    """Upload missing files from source_root tree to destination (an instance
    of a Destination subclass). Return tuple of (num_files_scanned,
    num_uploaded, num_errors).

    The contents of each source file is hashed, and hash_length hex digits of
    the hash are appended to the destination filename (key) as a "version", so
    that if a file changes, it's uploaded again under a new filename. For
    example, 'images/logo.png' will become something like
    'images/logo_deadbeef12345678.png'.

    If continue_on_errors is True, it will continue uploading other files even
    if some uploads fail (the default is to raise DestinationError on first
    error).

    If force is True, upload even if files are there already. If dry_run is
    True, log what would be uploaded instead of actually uploading. The
    dot_names, include, and exclude parameters are handled as per the
    walk_files() function.
    """
    source_key_map = build_key_map(
        source_root, hash_length=hash_length,
        dot_names=dot_names, include=include, exclude=exclude,
    )

    try:
        dest_keys = set(destination.keys())
    except Exception as error:
        raise DestinationError('ERROR listing keys at {}'.format(destination), error)

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
                    raise DestinationError('ERROR uploading to {}'.format(key), error, key=key)
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
    """Delete files from destination (an instance of a Destination subclass)
    that are no longer present in source_root tree. Return tuple of
    (num_files_scanned, num_deleted, num_errors).

    If continue_on_errors is True, it will continue deleting other files even
    if some deletes fail (the default is to raise DestinationError on first
    error).

    If dry_run is True, log what would be deleted instead of actually
    deleting. The dot_names, include, and exclude parameters are handled as
    per the walk_files() function.
    """
    source_key_map = build_key_map(
        source_root, hash_length=hash_length,
        dot_names=dot_names, include=include, exclude=exclude,
    )
    source_keys = set(source_key_map.values())

    try:
        dest_keys = sorted(destination.keys())
    except Exception as error:
        raise DestinationError('ERROR listing keys at {}'.format(destination), error)

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
                    raise DestinationError('ERROR deleting {}'.format(key), error, key=key)
                logger.error('ERROR deleting %s: %s', key, error)
                num_errors += 1
        else:
            num_deleted += 1

    logger.info('finished delete: deleted %d, errors with %d',
                num_deleted, num_errors)
    return (num_scanned, num_deleted, num_errors)


def main(args=None):
    """Command line endpoint for uploading/deleting. If args not specified,
    the sys.argv command line arguments are used. Run "cdnupload.py -h" for
    detailed help on the arguments.
    """
    if args is None:
        args = sys.argv[1:]

    description = """
Upload static files from given source directory to destination directory or
S3 bucket, with content-based hash in filenames for versioning.

cdnupload {version} -- Ben Hoyt (c) 2017 -- https://cdnupload.com/
""".format(version=__version__)

    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source',
                        help='source directory')
    parser.add_argument('destination',
                        help='destination directory (or s3://bucket/path)')
    parser.add_argument('dest_args', nargs='*', default=[],
                        help='optional Destination() keyword args, for example access-key=XYZ')
    parser.add_argument('-a', '--action', choices=['upload', 'delete', 'dest-help'], default='upload',
                        help='action to perform (upload, delete, or show help '
                             'for given Destination class), default %(default)s')
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
    parser.add_argument('-v', '--version', action='version', version=__version__)
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
    logging.basicConfig(level=logging.WARNING, format='%(message)s')
    logger.setLevel(log_levels[args.log_level])

    dest_kwargs = {}
    for arg in args.dest_args:
        name, sep, value = arg.partition('=')
        if not sep:
            value = True
        name = name.replace('-', '_')
        existing = dest_kwargs.get(name)
        if existing is not None:
            if isinstance(existing, list):
                existing.append(value)
            else:
                dest_kwargs[name] = [existing, value]
        else:
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

    if args.action == 'dest-help':
        import inspect
        import textwrap

        arg_spec = inspect.getargspec(destination_class.__init__)
        args_str = inspect.formatargspec(*arg_spec)
        if args_str.startswith('(self, '):
            args_str = '(' + args_str[7:]
        args_wrapped = textwrap.fill(
                args_str, width=79, initial_indent=' ' * 4,
                subsequent_indent=' ' * 5, break_long_words=False,
                break_on_hyphens=False)
        print('{}'.format(destination_class.__name__))
        print(args_wrapped)
        print()
        print(inspect.getdoc(destination_class))
        sys.exit(0)

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
            action_kwargs['force'] = args.force
            _, _, num_errors = upload(**action_kwargs)
        elif args.action == 'delete':
            _, _, num_errors = delete(**action_kwargs)
        else:
            assert 'unexpected action {!r}'.format(args.action)
    except DestinationError as error:
        logger.error('%s', error)
        num_errors = 1

    sys.exit(1 if num_errors else 0)


if __name__ == '__main__':
    main()
