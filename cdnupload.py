"""Upload static files to directory or CDN, using content-based hashing.

Run "python cdnupload.py -h" for command line help. See README.rst for
documentation, and LICENSE.txt for license information. Visit the project's
website for more information:

https://cdnupload.com/


TODO:
* tests
  - test handling of unicode filenames (round trip)
* python2 support
* cdnupload.com website, dual licensing, etc
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


class Error(Exception):
    """Base class that all exceptions raised in this module inherit from."""


class SourceError(Error):
    """Raised when an error occurs accessing the source (usually when building
    the key map).
    """

    def __init__(self, message, error):
        self.message = message
        self.error = error

    def __str__(self):
        return '{}: {}'.format(self.message, self.error)


class DeleteAllKeysError(Error):
    """Raised when delete() would delete all keys in destination."""


class DestinationError(Error):
    """Raised when an error occurs accessing the destination (usually
    uploading or deleting). Where relevant, includes the destination key in
    question.
    """

    def __init__(self, message, error, key=None):
        self.message = message
        self.error = error
        self.key = key

    def __str__(self):
        return '{}: {}'.format(self.message, self.error)


class FileSource(object):
    """Upload source that recursively returns files from directory tree
    starting at given root path. See __init__'s docstring for details.

    You can subclass this and pass the instance to upload() or delete() if you
    want to customize advanced behaviour like hash_file()'s text handling.
    """
    IS_TEXT_BYTES = 8000

    def __init__(self, root, dot_names=False, include=None, exclude=None,
                 ignore_walk_errors=False, follow_symlinks=False,
                 hash_length=DEFAULT_HASH_LENGTH, hash_chunk_size=64*1024,
                 hash_class=hashlib.sha1):
        """Initialize instance for sourcing file from given root directory.

        Include directories and files starting with '.' if "dot_names" is True
        (exclude them by default). If "include" is specified, only include
        relative paths that match "include" (per fnmatch), or one of the
        includes if tuple or list is given. If "exclude" is specified, exclude
        any relative paths that match "exclude", or one of the excludes if
        tuple or list is given.

        If ignore_walk_errors is True, ignore listdir errors when walking the
        source tree (except for the root directory, which is always considered
        an error). If follow_symlinks is True, follow symbolic links in the
        source tree (default is not to follow links).

        When building a key mapping, "hash_length" characters of the hex
        content hash are included in the filename. The file is read in
        "hash_chunk_size" blocks when being hashed. "hash_class" is called
        to generate the file hashes (you could use hashlib.md5 or something
        else instead).
        """
        self.root = root
        self.dot_names = dot_names

        if include and not isinstance(include, (tuple, list)):
            include = [include]
        self.include = include
        if exclude and not isinstance(exclude, (tuple, list)):
            exclude = [exclude]
        self.exclude = exclude

        self.ignore_walk_errors = ignore_walk_errors
        self.follow_symlinks = follow_symlinks
        self.os_walk = os.walk  # for easier testing

        self.hash_length = hash_length
        self.hash_chunk_size = hash_chunk_size
        self.hash_class = hash_class

    def __str__(self):
        """Return a human-readable string describing this source."""
        return self.root

    def open(self, rel_path):
        """Open file at given relative path."""
        path = os.path.join(self.root, rel_path)
        return open(path, 'rb')

    def hash_file(self, rel_path, is_text=None):
        """Read file at given relative path and return content hash as hex
        string (hash is SHA-1 hash of content).

        If is_text is None, determine whether file is text like Git does (it's
        treated as text if there's no NUL byte in first 8000 bytes).

        If file is text, the line endings are normalized to LF by stripping
        out any CR characters in the input. This is done to avoid hash
        differences between line endings on Windows (CR LF) and Linux/macOS
        (LF), especially with "automatic" line ending conversion when using
        Git or Subversion.
        """
        with self.open(rel_path) as file:
            chunk = file.read(self.hash_chunk_size)
            if is_text is None:
                is_text = chunk.find(b'\x00', 0, self.IS_TEXT_BYTES) == -1

            hash_obj = self.hash_class()
            while chunk:
                if is_text:
                    chunk = chunk.replace(b'\r', b'')
                hash_obj.update(chunk)
                chunk = file.read(self.hash_chunk_size)

        return hash_obj.hexdigest()

    def make_key(self, rel_path, file_hash):
        """Convert relative path and file hash to destination key, for
        example, a "rel_path" of 'images/logo.png' would become something like
        'images/logo_deadbeef12345678.png'.

        The number of characters in the hash part of the destiation key is
        specified by the "hash_length" initializer argument.
        """
        rel_file, ext = os.path.splitext(rel_path)
        key = '{}_{:.{}}{}'.format(rel_file, file_hash, self.hash_length, ext)
        return key

    def walk_files(self):
        """Generate list of relative paths starting at the source root and
        walking the directory tree recursively.

        Relative paths in the yielded values are canonicalized to always
        use use '/' (forward slash) as a path separator, regardless of running
        platform.
        """
        if sys.platform == 'win32' and isinstance(self.root, bytes):
            # Because os.walk() doesn't handle Unicode chars in walked paths
            # on Windows if a bytes path is specified (easy on Python 2.x with
            # "str")
            walk_root = self.root.decode(sys.getfilesystemencoding())
        else:
            walk_root = self.root

        # Ensure that errors while walking are raised as hard errors, unless
        # ignore_walk_errors is True or it's an error listing the root dir
        def onerror(error):
            if not self.ignore_walk_errors or error.filename == walk_root:
                raise error
            else:
                logger.debug('ignoring error scanning source tree: %s', error)

        walker = self.os_walk(walk_root, onerror=onerror,
                              followlinks=self.follow_symlinks)
        for root, dirs, files in walker:
            if not self.dot_names:
                dirs[:] = [d for d in dirs if not d.startswith('.')]

            for file in files:
                if not self.dot_names and file.startswith('.'):
                    continue

                rel_path = os.path.relpath(os.path.join(root, file), walk_root)
                rel_path = rel_path.replace('\\', '/')

                if self.include and not any(fnmatch.fnmatch(rel_path, i)
                                            for i in self.include):
                    continue
                if self.exclude and any(fnmatch.fnmatch(rel_path, e)
                                        for e in self.exclude):
                    continue

                yield rel_path

    def build_key_map(self):
        """Walk directory tree starting at source root and build a dict that
        maps relative path to key including content-based hash.

        The relative paths (keys of the returned dict) are "canonical",
        meaning '\' is converted to '/' on Windows, so that users of the
        mapping can always look up keys using 'dir/file.ext' style paths,
        regardless of operating system.
        """
        keys_by_path = {}
        for rel_path in self.walk_files():
            file_hash = self.hash_file(rel_path)
            key = self.make_key(rel_path, file_hash)
            keys_by_path[rel_path] = key
        return keys_by_path


class Destination(object):
    """Subclass this abstract base class to implement a destination uploader,
    for example uploading to Amazon S3, or to Google Cloud Storage.
    """

    def __init__(self, destination, **kwargs):
        """Initialize instance with given destination "URL", for example
        '/www/static' or 's3://bucket/key/prefix'. Format of destination arg
        and names of kwargs depend on the subclass.
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

    def upload(self, key, source, rel_path):
        """Upload single file from source instance and relative path to
        destination at "key".
        """
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

    def upload(self, key, source, rel_path):
        dest_path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with source.open(rel_path) as source_file:
            with open(dest_path, 'wb') as dest_file:
                shutil.copyfileobj(source_file, dest_file)

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
      region_name    AWS region name of S3 bucket (overrides boto3 default or
                     value in ~/.aws/config)
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

        client_kwargs = dict(
            region_name=region_name,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        if client_args:
            client_kwargs.update(client_args)
        self.s3_client = boto3.client('s3', **client_kwargs)

    def __str__(self):
        return 's3://{}/{}'.format(self.bucket_name, self.key_prefix)

    def keys(self):
        paginator = self.s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(
            Bucket=self.bucket_name,
            Prefix=self.key_prefix,
            PaginationConfig={'PageSize': 1000},
        )
        for response in pages:
            for obj in response.get('Contents', []):
                yield obj['Key']

    def upload(self, key, source, rel_path):
        content_type = mimetypes.guess_type(rel_path)[0]
        key = self.key_prefix + key

        extra_args = self.upload_args.copy()
        if content_type:
            extra_args['ContentType'] = content_type

        with source.open(rel_path) as source_file:
            self.s3_client.upload_fileobj(source_file, self.bucket_name, key,
                                          ExtraArgs=extra_args)

    def delete(self, key):
        key = self.key_prefix + key
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)


def upload(source, destination, force=False, dry_run=False,
           continue_on_errors=False):
    """Upload missing files from source to destination (an instance of a
    Destination subclass). Return tuple of (num_files_scanned, num_uploaded,
    num_errors).

    If "source" is a string, FileSource(source) is used as the source
    instance. Otherwise "source" must be a FileSource instance.

    The contents of each source file is hashed by the source and included in
    the destination key. This is so that if a file changes, it's uploaded
    again under a new filename to break caching. For example,
    'images/logo.png' will become something like
    'images/logo_deadbeef12345678.png'.

    If force is True, upload even if files are there already. If dry_run is
    True, log what would be uploaded instead of actually uploading.

    If continue_on_errors is True, it will continue uploading other files even
    if some uploads fail (the default is to raise DestinationError on first
    error).
    """
    if isinstance(source, (str, bytes)):
        source = FileSource(source)

    try:
        source_key_map = source.build_key_map()
    except Exception as error:
        raise SourceError('ERROR scanning source tree', error)

    try:
        dest_keys = set(destination.keys())
    except Exception as error:
        raise DestinationError('ERROR listing keys at {}'.format(destination),
                               error)

    options = []
    if force:
        options.append('force')
    if dry_run:
        options.append('dry_run')
    if continue_on_errors:
        options.append('continue_on_errors')
    logger.info('starting upload from %s (%d files) to %s (%d existing keys)%s',
                source,
                len(source_key_map),
                destination,
                len(dest_keys),
                ', options: ' + ', '.join(options) if options else '')

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
            try:
                destination.upload(key, source, rel_path)
                num_uploaded += 1
            except Exception as error:
                if not continue_on_errors:
                    raise DestinationError('ERROR uploading to {}'.format(key),
                                           error, key=key)
                logger.error('ERROR uploading to %s: %s', key, error)
                num_errors += 1
        else:
            num_uploaded += 1

    logger.info('finished upload: uploaded %d, skipped %d, errors with %d',
                num_uploaded, len(source_key_map) - num_uploaded, num_errors)
    return (num_scanned, num_uploaded, num_errors)


def delete(source, destination, force=False, dry_run=False,
           continue_on_errors=False):
    """Delete files from destination (an instance of a Destination subclass)
    that are no longer present in source tree. Return tuple of
    (num_files_scanned, num_deleted, num_errors).

    If "source" is a string, FileSource(source) is used as the source
    instance. Otherwise "source" must be a FileSource instance.

    This function does a sanity check to ensure you're not deleting ALL keys
    at the destination by accident (for example, specifying an empty directory
    for the source tree). If it would delete all destination keys, it raises
    DeleteAllKeysError. To override and delete all anyway, specify force=True.

    If dry_run is True, log what would be deleted instead of actually
    deleting.

    If continue_on_errors is True, it will continue deleting other files even
    if some deletes fail (the default is to raise DestinationError on first
    error).
    """
    if isinstance(source, (str, bytes)):
        source = FileSource(source)

    try:
        source_key_map = source.build_key_map()
    except Exception as error:
        raise SourceError('ERROR scanning source tree', error)
    source_keys = set(source_key_map.values())

    try:
        dest_keys = sorted(destination.keys())
    except Exception as error:
        raise DestinationError('ERROR listing keys at {}'.format(destination),
                               error)

    options = []
    if dry_run:
        options.append('dry_run')
    if continue_on_errors:
        options.append('continue_on_errors')
    logger.info('starting delete from %s (%d files) to %s (%d existing keys)%s',
                source,
                len(source_key_map),
                destination,
                len(dest_keys),
                ', options: ' + ', '.join(options) if options else '')

    if not force:
        num_to_delete = sum(1 for k in dest_keys if k not in source_keys)
        if num_to_delete >= len(dest_keys):
            raise DeleteAllKeysError(
                    "ERROR - would delete all {} destination keys, "
                    "you probably didn't intend this! (use -f/--force or "
                    "force=True to override)".format(len(dest_keys)))

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
                    raise DestinationError('ERROR deleting {}'.format(key),
                                           error, key=key)
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
cdnupload {version} -- (c) Ben Hoyt 2017 -- https://cdnupload.com/

Upload static files from given source directory to destination directory or
Amazon S3 bucket, with content-based hash in filenames for versioning.
""".format(version=__version__)

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument('source',
                        help='source directory')
    parser.add_argument('destination',
                        help='destination directory (or s3://bucket/path)')
    parser.add_argument('dest_args', nargs='*', default=[],
                        help='optional Destination() keyword args, for example '
                             'access-key=XYZ')

    parser.add_argument('-a', '--action', default='upload',
                        choices=['upload', 'delete', 'dest-help'],
                        help='action to perform (upload, delete, or show help '
                             'for given Destination class), default %(default)s')
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help='show what script would upload or delete instead of '
                             'actually doing it')
    parser.add_argument('-e', '--exclude', action='append', metavar='PATTERN',
                        help='exclude source file if its relative path '
                             'matches, for example *.txt or __pycache__/* '
                             '(may be specified multiple times)')
    parser.add_argument('-f', '--force', action='store_true',
                        help='force upload even if destination file already exists, '
                             'or force delete even if it would delete all keys at '
                             'destination')
    parser.add_argument('-i', '--include', action='append', metavar='PATTERN',
                        help='only include source file if its relative path '
                             'matches, for example *.png or images/* (may be '
                             'specified multiple times)')
    parser.add_argument('-l', '--log-level', default='default',
                        choices=['verbose', 'default', 'quiet', 'errors', 'off'],
                        help='set logging level')
    parser.add_argument('-v', '--version', action='version', version=__version__)

    less_common = parser.add_argument_group('less commonly-used arguments')
    less_common.add_argument('--continue-on-errors', action='store_true',
                             help='continue after upload or delete errors')
    less_common.add_argument('--dot-names', action='store_true',
                             help="include source files and directories starting "
                                  "with '.'")
    less_common.add_argument('--follow-symlinks', action='store_true',
                             help='follow symbolic links when walking source tree')
    less_common.add_argument('--hash-length', default=DEFAULT_HASH_LENGTH,
                             type=int, metavar='N',
                             help='number of hex chars of hash to use for '
                                  'destination key (default %(default)d)')
    less_common.add_argument('--ignore-walk-errors', action='store_true',
                             help='ignore errors when walking source tree, '
                                  'except for error on root directory')

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
                parser.error('{} module has no Destination class'.format(
                        module_name))
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

    source = FileSource(
        args.source,
        dot_names=args.dot_names,
        include=args.include,
        exclude=args.exclude,
        ignore_walk_errors=args.ignore_walk_errors,
        follow_symlinks=args.follow_symlinks,
        hash_length=args.hash_length,
    )

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

    try:
        destination = destination_class(args.destination, **dest_kwargs)
    except Exception as error:
        logger.error('ERROR creating %s instance: %s',
                     destination_class.__name__, error)
        sys.exit(1)

    action_args = dict(
        source=source,
        destination=destination,
        force=args.force,
        dry_run=args.dry_run,
        continue_on_errors=args.continue_on_errors,
    )
    try:
        if args.action == 'upload':
            _, _, num_errors = upload(**action_args)
        elif args.action == 'delete':
            _, _, num_errors = delete(**action_args)
        else:
            assert 'unexpected action {!r}'.format(args.action)
    except Error as error:
        logger.error('%s', error)
        num_errors = 1

    sys.exit(1 if num_errors else 0)


if __name__ == '__main__':
    main()
