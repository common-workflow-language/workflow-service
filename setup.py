#!/usr/bin/env python

import os
from setuptools import setup

SETUP_DIR = os.path.dirname(__file__)

long_description = ""

with open("README.pypi.rst") as readmeFile:
    long_description = readmeFile.read()

setup(name='wes-service',
      version='3.3',
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
          'connexion >= 2.0.2, < 3',
          'ruamel.yaml >= 0.12.4, <= 0.15.77',
          'schema-salad',
          'subprocess32==3.5.2'
                        ],
      entry_points={
          'console_scripts': ["wes-server=wes_service.wes_service_main:main",
                              "wes-client=wes_client.wes_client_main:main"]
                    },
      extras_require={
          "cwltool": ['cwlref-runner'],
          "arvados": ["arvados-cwl-runner"
                      ],
          "toil": ["toil[all]==3.24.0"
                   ]},
      zip_safe=False,
      platforms=['MacOS X', 'Posix'],
      classifiers=[
          'Intended Audience :: Developers',
          'License :: OSI Approved :: Apache Software License',
          'Operating System :: MacOS :: MacOS X',
          'Operating System :: POSIX',
          'Programming Language :: Python',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Topic :: Software Development :: Libraries :: Python Modules'
        ]
      )
