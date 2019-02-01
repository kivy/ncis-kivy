"""
NCIS - Not a Clever Inspector Service - Kivy module
"""

from setuptools import setup, find_packages
from os import path
from io import open

here = path.abspath(path.dirname(__file__))
with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="ncis-kivy",
    version="0.1",
    description="Kivy plugin for NCIS",
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/kivy/ncis-kivy',
    author='Kivy Team',
    author_email='kivy-dev@googlegroups.com',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=['ncis'],
    project_urls={
        'Bug Reports': 'https://github.com/kivy/ncis-kivy/issues',
        'Source': 'https://github.com/kivy/ncis-kivy/',
    },
)
