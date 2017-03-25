
=========
cdnupload
=========

--------------------------
Documentation and examples
--------------------------


Introduction
============

cdnupload uploads your website’s static files to a CDN with a content-based hash in the filename, giving great caching while avoiding versioning issues.


How it works
------------

TODO

For a brief introduction to what a CDN is and why you might want to use one, `see the CDN section on the cdnupload homepage. <https://cdnupload.com/#cdn>`_


Multi-licensing
---------------

cdnupload is © Ben Hoyt 2017 and licensed under multiple licenses (`read why here <https://cdnupload.com/#licensing>`_). It’s free for open source websites and non-profits, and there are two well-priced commercial licenses available for businesses. The three license options are:

1. **Open:** if the code for your website is open source, or if you’re a non-profit organization, you can use cdnupload for free under an AGPL license. `Read the full text of the AGPL v3 license. <https://www.gnu.org/licenses/agpl-3.0.en.html>`_

2. **Single website:** if your business has a single website, this commercial license tier is for you. `See pricing, more details, and the full text of the single website license. <https://cdnupload.com/single>`_

3. **Multi-website:** this license is a commercial license for using cdnupload on up to 10 websites. `See pricing, more details, and the full text of the multi-website license. <https://cdnupload.com/multi>`_

If your company’s requirements don’t fit into any of the above, or you want to discuss a custom license, please contact us at `info@cdnupload.com <mailto:info@cdnupload.com>`_.


Command-line usage
------------------

TODO


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
