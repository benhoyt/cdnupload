
from urllib.parse import urlparse
import mimetypes

import cdnupload


class Destination(cdnupload.Destination):
    def __init__(self, s3_url):
        parsed = urlparse(s3_url)
        if parsed.scheme != 's3':
            raise ValueError('s3_url must start with s3://')
        if not parsed.netloc:
            raise ValueErrro('s3_url must include a bucket name')
        self.bucket_name = parsed.netloc
        self.key_prefix = parsed.path.lstrip('/')

    def __str__(self):
        return 's3://{}/{}'.format(self.bucket_name, self.key_prefix)

    def keys(self):
        pass

    def upload(self, key, source_path):
        content_type = mimetypes.guess_type(source_path)[0]

    def delete(self, key):
        pass
