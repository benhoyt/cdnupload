
=========
cdnupload
=========

-------------
Documentation
-------------


Introduction
============

cdnupload uploads your website’s static files to a CDN with a content-based hash in the filename, giving great caching while avoiding versioning issues.

Read this documentation online for best results: https://cdnupload.com/docs


Multi-licensing
===============

cdnupload is © Ben Hoyt 2017 and licensed under multiple licenses (`read why here <https://cdnupload.com/#licensing>`_). It’s free for open source websites and non-profits, and there are two well-priced commercial licenses available for businesses. The three license options are:

1. **Open:** if the code for your website is open source, or if you’re a non-profit organization, you can use cdnupload for free under an AGPL license. `Read the full text of the AGPL v3 license. <https://www.gnu.org/licenses/agpl-3.0.en.html>`_

2. **Single website:** if your business has a single website, this commercial license tier is for you. `See pricing, more details, and the full text of the single website license. <https://cdnupload.com/single>`_

3. **Multi-website:** this license is a commercial license for using cdnupload on up to 10 websites. `See pricing, more details, and the full text of the multi-website license. <https://cdnupload.com/multi>`_

If your company’s requirements don’t fit into any of the above, or you want to discuss a custom license, please contact us at `info@cdnupload.com <mailto:info@cdnupload.com>`_.


Overview
========

cdnupload is primarily a **command-line tool** that uploads your site's static files to a CDN (well, really the CDN's origin server). It optionally generates a JSON "key mapping" that maps filename to destination key. The destination key is the filename with a hash in it based on the file's contents. This allows you to set up the CDN to cache your static files aggresively, with an essentially infinite expiry time (max age).

(For a brief introduction to what a CDN is and why you might want to use one, `see the CDN section on the cdnupload homepage. <https://cdnupload.com/#cdn>`_)

When you upload statics, you specify a source directory and a destination directory (or Amazon S3 or other origin server pseudo-URL). For example, you can upload all the static files from the ``/website/static`` directory to ``static-bucket``, and output the key mapping to the file ``statics.json`` using the following command::

    cdnupload /website/static s3://static-bucket --key-map=statics.json

The uploader will walk the source directory tree, query the destination S3 bucket (or directory), and upload any files that are missing. For example, if you have one JavaScript file and two CSS files, the output of the tool might look something like this::

    uploading script.js to script_0beec7b5ea3f0fdb.js
    uploading style.css to style_62cdb7020ff920e5.css
    uploading mobile.css to mobile_bbe960a25ea311d2.css
    writing key map JSON to statics.json

If you modify mobile.css and then run it again, you'll see that it only uploads the changed files::

    uploading mobile.css to mobile_6b369e490de120a9.css
    writing key map JSON to statics.json

It doesn’t delete unused files on the destination directory automatically (as the currently-deployed website is probably still using them). To do that, you need to use the delete action::

    cdnupload /website/static s3://static-bucket --action=delete

Here's what the output might be after the above uploads::

    deleting mobile_bbe960a25ea311d2.css

There are many command-line options to control what files to upload, change the destination parameters, etc. And you can use the Python API directly if you need advanced features or if you need to add another destination "provider". See details in the `command-line usage section below. <#command-line-usage>`_

You'll also need to **integrate with your web server** so that your web application knows the hash mapping and can output the correct static URLs. That can be as simple as a ``static_url`` template function that uses the key map JSON to convert from a file path to the destination key. See details in the `web server integration section below. <#web-server-integration>`_


Command-line usage
==================

The basic format of the cdnupload command line is::

    cdnupload [options] source destination [dest_args]

Where ``options`` are short or long (``-s`` or ``--long``) command line options. You can mix these freely with the positional arguments if you want.

Source
------

``source`` is the source directory of your static files, for example ``/website/static``. Use the optional ``--include`` and ``--exclude`` arguments, and other arguments described below, to control exactly which files are uploaded.

Destination and dest-args
-------------------------

``destination`` is the destination directory to upload to, or an ``s3://static-bucket/key/prefix`` path for upload to Amazon S3.

You can also specify a custom scheme for the destination (the ``scheme://`` part of the URL), and cdnupload will try to import a module named ``cdnupload_scheme`` (which must be on the ``PYTHONPATH``) and use that module's ``Destination`` class along with the ``dest_args`` to create the destination instance.

For example, if you create your own uploader for Google Cloud Storage, you might use the prefix ``gcs://`` and name your module ``cdnupload_gcs``. Then you could use ``gcs://my/path`` as a destination, and cdnupload would instantiate the destination instance using ``cdnupload_gcs.Destination('gcs://bucket', **dest_args)``.

For more details about custom ``Destination`` subclasses, see below (TODO).

``dest_args`` are destination-specific arguments passed as keyword arguments to the ``Destination`` class (for example, for ``s3://`` destinations, useful dest args are ``max_age=86400`` or ``region_name=s3_region``). For help on destination-specific args, use the ``dest-help`` action. For example, to show S3-specific destination args::

    cdnupload source s3:// --action=dest-help

Common arguments
----------------

  -h, --help
        Show help about these command-line options and exit.

  -a ACTION, --action ACTION
        Specify action to perform (the default is to upload):

        * ``upload``: Upload files that are not present at the destination from the source to the destination.
        * ``delete``: Delete unused files at the destination (files no longer present at the source). Be careful with deleting, and use ``--dry-run`` to test first!
        * ``dest-help``: Show help and available destination arguments for the given Destination class.

  -d, --dry-run
        Show what the script would upload or delete instead of actually doing it. This option is recommended before running with ``--action=delete``, to ensure you're not deleting more than you expect.

  -e PATTERN, --exclude PATTERN
        Exclude source files if their relative path matches the given pattern (according to globbing rules as per Python's ``fnmatch``). For example, ``*.txt`` to include all text files, or ``__pycache__/*`` to exclude everything under the *pycache* directory. This option may be specified multiple times to exclude more than one pattern.

        Excludes take precedence over includes, so you can do ``--include=*.txt`` but then exclude a specific text file with ``--exclude=docs/README.txt``.

  -f, --force
        If uploading, force all files to be uploaded even if destination files already exist (useful, for example, when updating headers on Amazon S3).

        If deleting, allow the delete to occur even if all files on the destination would be deleted (the default is to prevent that to avoid ``rm -rf`` style mistakes).

  -i PATTERN, --include PATTERN
        If specified, only include source files if their relative path matches the given pattern (according to globbing rules as per Python's ``fnmatch``). For example, ``*.png`` to include all PNG images, or ``images/*`` to include everything under the *images* directory. This option may be specified multiple times to include more than one pattern.

        Excludes take precedence over includes, so you can do ``--include=*.txt`` but then exclude a specific text file with ``--exclude=docs/README.txt``.

  -k FILENAME, --key-map FILENAME
        Write key mapping to given file as JSON (but only after successful upload or delete). This file can be used by your web server to produce full CDN URLs for your static files.

        Keys in the JSON object are the original paths (relative to the source root), and values in the object are the destination paths (relative to the destination root). For example, the JSON might look like ``{"script.js": "script_0beec7b5ea3f0fdb.js", ...}``.

  -l LEVEL, --log-level LEVEL
        Set the verbosity of the log output. The level must be one of:

        * ``verbose``: Most verbose output. Log even files that the script would skip uploading.
        * ``default``: Default level of output. Log when the script starts, finishes, and actual uploads and deletes that occur (or would occur if doing a ``--dry-run``).
        * ``quiet``: Quieter than the default. Only log when and if the script actually uploads or deletes files (no start or finish logs). If there's nothing to do, don't log anything.
        * ``errors``: Only log errors.
        * ``off``: Turn all logging off completely.

  -v, --version
        Show cdnupload's version number and exit.

Less common arguments
---------------------

  --continue-on-errors
        Continue after upload or delete errors. The script will still log the errors, and it will also return a nonzero exit code if there is at least one error. The default is to stop on the first error.
  --dot-names
        Include source files and directories that start with ``.`` (dot). The default is to skip any files or directories that start with a dot.
  --follow-symlinks
        Follow symbolic links to directories when walking the source tree. The default is to skip any symbolic links to directories.
  --hash-length N
        Set the number of hexadecimal characters of the content hash to use for destination key. The default is 16.
  --ignore-walk-errors
        Ignore errors when walking the source tree (for example, permissions errors on a directory), except for an error when listing the source root directory.


Web server integration
======================

In addition to using the command line script to upload files, you'll need to modify your web server so it knows how to generate the static URLs including the content-based hash in the filename.

The recommended way to do this is to load the key mapping JSON, which is written out by the ``--key-map`` command line argument when you upload your statics. You can load this into a key-value dictionary when your server starts up, and then generating a static URL is as simple as looking up the relative path of a static file in this dictionary.

Even though the keys in the JSON are relative file paths, they're normalized to always use ``/`` (forward slash) as the directory separator, even on Windows. This is so consumers of the mapping can look up files directly in the mapping with a consistent path separator.

Below is a simple example of loading the key mapping in your web server startup (call ``init_server()`` on startup) and then defining a function to generate full static URLs for use in your HTML templates. This example is written in Python, but you can use any language that can parse JSON and look something up in a map::

    import json
    import settings

    def init_server():
        settings.cdn_base_url = 'https://mycdn.com/'
        with open('statics.json') as f:
            settings.statics = json.load(f)

    def static_url(rel_path):
        """Convert relative static path to full static URL (including hash)"""
        return settings.cdn_base_url + settings.statics[rel_path]

And then in your HTML templates, just reference a static file using the ``static_url`` function (referenced here as a Jinja2 template filter)::

    <link rel="stylesheet" href="{{ 'style.css'|static_url }}">

If your web server is in fact written in Python, you can also ``import cdnupload`` directly and use ``cdnupload.FileSource`` with the same parameters as the upload command line. This will build the key mapping at server startup time, and may simplify the deployment process a little::

    import cdnupload
    import settings

    def init_server():
        settings.cdn_base_url = 'https://mycdn.com/'
        source = cdnupload.FileSource(settings.static_dir)
        settings.static_paths = source.build_key_map()

If you have huge numbers of static files, this is not recommended, as it does have to re-hash all the files when the server starts up. So for larger sites it's best to produce the key map JSON and copy that to your app servers as part of your deployment process.


Static URLs in CSS
==================

TODO


Python API
==========

TODO


About the author
================

cdnupload is written and maintained by Ben Hoyt: a `software developer <http://benhoyt.com/cv/>`_, `Python contributor <http://benhoyt.com/writings/scandir/>`_, and general all-round computer geek. `Read how and why he wrote cdnupload. <http://TODO>`_
