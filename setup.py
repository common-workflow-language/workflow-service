#!/usr/bin/env python

import os
import sys
import setuptools.command.egg_info as egg_info_cmd
import shutil

from setuptools import setup, find_packages

SETUP_DIR = os.path.dirname(__file__)
README = os.path.join(SETUP_DIR, 'README')

setup(name='cwltool_service',
      version='2.0',
      description='Common workflow language runner service',
      long_description=open(README).read(),
      author='Common workflow language working group',
      author_email='common-workflow-language@googlegroups.com',
      url="https://github.com/common-workflow-language/common-workflow-language",
      download_url="https://github.com/common-workflow-language/common-workflow-language",
      license='Apache 2.0',
      py_modules=["cwltool_stream", "cwl_flask", "cwltool_client"],
      install_requires=[
          'cwltool >= 1.0.20151013135545',
          'Flask',
          'requests',
          'yaml'
        ],
      entry_points={
          'console_scripts': [ "cwltool-stream=cwltool_stream:main",
                               "cwl-server=cwl_flask:main",
                               "cwl-client=cwl_client:main"]
      },
      zip_safe=True
)
