"""Run 'python setup.py install' to install cdnupload."""

import os
import re
from setuptools import setup


# Because it's best not to import the module in setup.py
with open(os.path.join(os.path.dirname(__file__), 'cdnupload.py')) as f:
    for line in f:
        match = re.match(r"__version__.*'([0-9.]+)'", line)
        if match:
            version = match.group(1)
            break
    else:
        raise Exception("Couldn't find __version__ line in cdnupload.py")


# Read long_description from README.rst
with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as f:
    long_description = f.read()


setup(
    name='cdnupload',
    version=version,
    author='Ben Hoyt',
    author_email='benhoyt@gmail.com',
    url='https://cdnupload.com/',
    license='Multi-licensed: AGPLv3 and Commercial',
    description='Upload static files from given source directory to '
                'destination directory or Amazon S3 bucket, with content-'
                'based hash in filenames for versioning.',
    long_description=long_description,
    py_modules=['cdnupload'],
    extras_require={
        's3': ['boto3'],
    },
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    entry_points={
        'console_scripts': ['cdnupload = cdnupload:main'],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'License :: Other/Proprietary License',
        'Programming Language :: Python',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Internet :: WWW/HTTP',
    ],
)
