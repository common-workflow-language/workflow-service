from __future__ import absolute_import

import unittest
import os
import logging
import subprocess

from wes_client.util import expand_globs

logging.basicConfig(level=logging.INFO)


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        dirname, filename = os.path.split(os.path.abspath(__file__))
        self.testdata_dir = dirname + 'data'

    def tearDown(self):
        unittest.TestCase.tearDown(self)

    def test_expand_globs(self):
        """Asserts that wes_client.expand_globs() sees the same files in the cwd as 'ls'."""
        files = subprocess.check_output(['ls', '-1', '.'])

        # python 2/3 bytestring/utf-8 compatibility
        if isinstance(files, str):
            files = files.split('\n')
        else:
            files = files.decode('utf-8').split('\n')

        if '' in files:
            files.remove('')
        files = ['file://' + os.path.abspath(f) for f in files]
        glob_files = expand_globs('*')
        assert set(files) == glob_files, '\n' + str(set(files)) + '\n' + str(glob_files)


if __name__ == '__main__':
    unittest.main()  # run all tests
