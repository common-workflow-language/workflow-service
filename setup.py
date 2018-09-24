#!/usr/bin/env python

import os
from setuptools import setup

SETUP_DIR = os.path.dirname(__file__)

long_description = ""

with open("README.pypi.rst") as readmeFile:
    long_description = readmeFile.read()

setup(name='wes-service',
      version='2.8',
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
          'future',
          'connexion==1.4.2',
          'ruamel.yaml >= 0.12.4, < 0.15',
          'cwlref-runner==1.0',
          'schema-salad>=2.6, <3',
          'subprocess32==3.5.2'
                        ],
      entry_points={
          'console_scripts': ["wes-server=wes_service.wes_service_main:main",
                              "wes-client=wes_client.wes_client_main:main"]
                    },
      extras_require={
          "arvados": ["arvados-cwl-runner"
                      ],
          "toil": ["toil[all]==3.16.0"
                   ]},
      zip_safe=False
      )
