
=========
cdnupload
=========

--------------------------
Documentation and examples
--------------------------


Introduction
============

cdnupload uploads your website’s static files to a CDN with a content-based hash in the filename, giving great caching while avoiding versioning issues.


Multi-licensing
---------------

cdnupload is © Ben Hoyt 2017 and licensed under multiple licenses (`read why here <https://cdnupload.com/#licensing>`_). It’s free for open source websites and non-profits, and there are two well-priced commercial licenses available for businesses. The three license options are:

1. **Open:** if the code for your website is open source, or if you’re a non-profit organization, you can use cdnupload for free under an AGPL license. `Read the full text of the AGPL v3 license. <https://www.gnu.org/licenses/agpl-3.0.en.html>`_

2. **Single website:** if your business has a single website, this commercial license tier is for you. `See pricing, more details, and the full text of the single website license. <https://cdnupload.com/single>`_

3. **Multi-website:** this license is a commercial license for using cdnupload on up to 10 websites. `See pricing, more details, and the full text of the multi-website license. <https://cdnupload.com/multi>`_

If your company’s requirements don’t fit into any of the above, or you want to discuss a custom license, please contact us at `info@cdnupload.com <mailto:info@cdnupload.com>`_.


How it works
------------

cdnupload is primarily a **command-line tool** that uploads the static files to a CDN (well, really the CDN's origin server). It optionally generates a JSON "key mapping" that maps filename to destination key. The destination key is the filename with a hash in it based on the file's contents. This allows you to set up the CDN to cache your static files aggresively, with an essentially infinite expiry time (max age).

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
------------------

The basic format of the cdnupload command line is::

    cdnupload [options] source destination [dest_args]

Where ``options`` are short or long (``-s`` or ``--long``) command line options. You can mix these freely with the positional arguments if you want.

Source
~~~~~~

``source`` is the source directory of your static files, for example ``/website/static``. Use the optional ``--include`` and ``--exclude`` arguments, and other arguments described below, to control exactly which files are uploaded.

Destination and dest-args
~~~~~~~~~~~~~~~~~~~~~~~~~

``destination`` is the destination directory to upload to, or an ``s3://static-bucket/key/prefix`` path for upload to Amazon S3.

You can also specify a custom scheme for the destination (the ``scheme://`` part of the URL), and cdnupload will try to import a module named ``cdnupload_scheme`` (which must be on the ``PYTHONPATH``) and use that module's ``Destination`` class along with the ``dest_args`` to create the destination instance.

For example, if you create your own uploader for Google Cloud Storage, you might use the prefix ``gcs://`` and name your module ``cdnupload_gcs``. Then you could use ``gcs://my/path`` as a destination, and cdnupload would instantiate the destination instance using ``cdnupload_gcs.Destination('gcs://bucket', **dest_args)``.

For more details about custom ``Destination`` subclasses, see below (TODO).

``dest_args`` are destination-specific arguments passed as keyword arguments to the ``Destination`` class (for example, for ``s3://`` destinations, useful dest args are ``max_age=86400`` or ``region_name=s3_region``). For help on destination-specific args, use the ``dest-help`` action. For example, to show S3-specific destination args::

    cdnupload source s3:// --action=dest-help

Optional arguments
~~~~~~~~~~~~~~~~~~

The most common optional arguments are:

  -h, --help            Show help about these command-line options and exit.

  -a ACTION, --action ACTION
                        Specify action to perform (the default is to upload):

                        * ``upload``: Upload files that are not present at the destination from the source to the destination.
                        * ``delete``: Delete unused files at the destination (files no longer present at the source). Be careful with deleting, and use ``--dry-run`` to test first!
                        * ``dest-help``: Show help and available destination arguments for the given Destination class.

  -d, --dry-run         Show what the script would upload or delete instead of actually doing it. This option is recommended before running with ``--action=delete``, to ensure you're not deleting more than you expect.

  -e PATTERN, --exclude PATTERN
                        Exclude source files if their relative path matches the given pattern (according to globbing rules as per Python's ``fnmatch``). For example, ``*.txt`` to include all text files, or ``__pycache__/*`` to exclude everything under the *pycache* directory. This option may be specified multiple times to exclude more than one pattern.

                        Excludes take precedence over includes, so you can do ``--include=*.txt`` but then exclude a specific text file with ``--exclude=docs/README.txt``.

  -f, --force           If uploading, force all files to be uploaded even if destination files already exist (useful, for example, when updating headers on Amazon S3).

                        If deleting, allow the delete to occur even if all files on the destination would be deleted (the default is to prevent that to avoid ``rm -rf`` style mistakes).

  -i PATTERN, --include PATTERN
                        If specified, only include source files if their relative path matches the given pattern (according to globbing rules as per Python's ``fnmatch``). For example, ``*.png`` to include all PNG images, or ``images/*`` to include everything under the *images* directory. This option may be specified multiple times to include more than one pattern.

                        Excludes take precedence over includes, so you can do ``--include=*.txt`` but then exclude a specific text file with ``--exclude=docs/README.txt``.

  -k FILENAME, --key-map FILENAME
                        Write key mapping to given file as JSON (but only
                        after successful upload or delete). This file can be used by your web server to produce full CDN URLs for your static files.

                        Keys in the JSON object are the original paths (relative to the source root), and values in the object are the destination paths (relative to the destination root). For example, the JSON might look like: ``TODO``

  -l LEVEL, --log-level LEVEL
                        set logging level

  -v, --version         show program's version number and exit

Less commonly-used arguments are:

TODO


Web server integration
----------------------

For example::

    import json, settings

    def init_server():
        """Load the key map JSON written by cdnupload --key-map"""
        with open('statics.json') as f:
            settings.statics = json.load(f)

    def static_url(rel_path):
        """Convert relative static path to full static URL (including hash)"""
        return '//mycdn.com/' + settings.statics[rel_path]

And then in your HTML templates, just reference a static file using the ``static_url`` filter (Jinja2 template example)::

    {{ ' style.css'|static_url }}

There are various ways to integrate cdnupload, particularly in Python where you can ``import cdnupload`` and build the key map directly if you want. Read on for full details.


Static URLs in CSS
------------------

TODO


Python API
----------

TODO



Examples
--------

Example usage::

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


About the author
----------------

cdnupload is written and maintained by Ben Hoyt: a `software developer <http://benhoyt.com/cv/>`_, `Python contributor <http://benhoyt.com/writings/scandir/>`_, and general all-round computer geek. `Read how and why he wrote cdnupload. <http://TODO>`_
