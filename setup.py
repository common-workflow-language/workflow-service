#!/usr/bin/env python

import os
import sys
import setuptools.command.egg_info as egg_info_cmd
import shutil

from setuptools import setup, find_packages

SETUP_DIR = os.path.dirname(__file__)

long_description = ""

with open("README.pypi.rst") as readmeFile:
    long_description = readmeFile.read()

setup(name='wes-service',
      version='2.4',
      description='GA4GH Workflow Execution Service reference implementation',
      long_description=long_description,
      author='GA4GH Containers and Workflows task team',
      author_email='common-workflow-language@googlegroups.com',
      url="https://github.com/common-workflow-language/cwltool-service",
      download_url="https://github.com/common-workflow-language/cwltool-service",
      license='Apache 2.0',
      packages=["wes_service", "wes_client"],
      package_data={'wes_service': ['openapi/workflow_execution_service.swagger.yaml']},
      include_package_data=True,
      install_requires=[
          'connexion',
          'bravado',
          'ruamel.yaml >= 0.12.4, < 0.15',
          'cwlref-runner',
          'schema-salad'
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
      zip_safe=False
)
