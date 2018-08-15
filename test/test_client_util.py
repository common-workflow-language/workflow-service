from __future__ import absolute_import

import unittest
import os
import logging
import subprocess
import sys

pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))  # noqa
sys.path.insert(0, pkg_root)  # noqa

from wes_client.util import expand_globs, wf_info

logging.basicConfig(level=logging.INFO)


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        dirname, filename = os.path.split(os.path.abspath(__file__))
        self.testdata_dir = dirname + 'data'
        self.local = {'cwl': 'file://' + os.path.join(os.getcwd() + '/testdata/md5sum.cwl'),
                 'wdl': 'file://' + os.path.join(os.getcwd() + '/testdata/md5sum.wdl'),
                 'py': 'file://' + os.path.join(os.getcwd() + '/test/test_integration.py'),
                 'unsupported': 'fake.txt'}

        self.remote = {
            'cwl': 'https://raw.githubusercontent.com/common-workflow-language/workflow-service/master/testdata/md5sum.cwl',
            'wdl': 'https://raw.githubusercontent.com/common-workflow-language/workflow-service/master/testdata/md5sum.wdl',
            'py': 'https://raw.githubusercontent.com/common-workflow-language/workflow-service/master/test/test_integration.py',
            'unsupported': 'gs://topmed_workflow_testing/topmed_aligner/small_test_files_sbg/example_human_known_snp.py',
            'unreachable': 'https://fake.py'}

        self.expected = {'cwl': ('v1.0', 'CWL'),
                    'wdl': ('draft-2', 'WDL'),
                    'py': ('2.7', 'PY'),
                    'pyWithPrefix': ('2.7', 'PY')}

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

    def testSupportedFormatChecking(self):
        """
        Check that non-wdl, -python, -cwl files are rejected.

        This test is run only on local files to avoid downloading and removing a new file.
        """

        for file_format, location in self.local.items():
            if file_format != 'unsupported':
                # Tests the behavior after receiving supported file types with and without the 'file://' prefix
                self.assertEquals(wf_info(location), self.expected[file_format])
                self.assertEquals(wf_info(location[7:]), self.expected[file_format])

            else:
                # Tests behavior after receiving a non supported file type.
                with self.assertRaises(TypeError):
                    wf_info(location)

    def testFileLocationChecking(self):
        """
        Check that the function rejects unsupported file locations.

        This test needs to be run on remote files to test the location checking functionality of wf_info().
        """

        for file_format, location in self.remote.items():
            if file_format == 'unsupported':
                # Tests behavior after receiving a file hosted at an unsupported location.
                with self.assertRaises(NotImplementedError):
                    wf_info(location)

            elif file_format == 'unreachable':
                # Tests behavior after receiving a non-existent file.
                with self.assertRaises(IOError):
                    wf_info(location)

            else:
                self.assertEquals(wf_info(location), self.expected[file_format])
                self.assertFalse(os.path.isfile(os.path.join(os.getcwd(), 'fetchedFromRemote.' + file_format)))


if __name__ == '__main__':
    unittest.main()  # run all tests
