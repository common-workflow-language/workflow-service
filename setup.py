#!/usr/bin/env python

import os
import sys
import setuptools.command.egg_info as egg_info_cmd
import shutil

from setuptools import setup, find_packages

SETUP_DIR = os.path.dirname(__file__)
README = os.path.join(SETUP_DIR, 'README.md')

setup(name='wes-service',
      version='2.1',
      description='GA4GH Workflow Execution Service reference implementation',
      long_description=open(README).read(),
      author='GA4GH Containers and Workflows task team',
      author_email='common-workflow-language@googlegroups.com',
      url="https://github.com/common-workflow-language/cwltool-service",
      download_url="https://github.com/common-workflow-language/cwltool-service",
      license='Apache 2.0',
      packages=["wes_service", "wes_client"],
      package_data={'wes_service': ['swagger/proto/workflow_execution.swagger.json']},
      include_package_data=True,
      install_requires=[
          'connexion',
          'bravado',
          'ruamel.yaml >= 0.12.4, < 0.15',
        ],
      entry_points={
          'console_scripts': [ "wes-server=wes_service:main",
                               "wes-client=wes_client:main"]
      },
      extras_require={
          "arvados": [
              "arvados-cwl-runner"
          ]
      },
      zip_safe=True
)
