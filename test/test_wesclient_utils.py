import unittest
import os
from wes_client.util import wf_info

class WorkflowInfoTest(unittest.TestCase):

    local = {'cwl': 'file://' + os.path.join(os.getcwd() + '/workflow-service/testdata/md5sum.cwl'),
             'wdl': 'file://' + os.path.join(os.getcwd() + '/workflow-service/testdata/md5sum.wdl'),
             'py': 'file://' + os.path.join(os.getcwd() + '/workflow-service/test/test_integration.py'),
             'unsupported':'fake.txt'}

    remote = {'cwl':'https://raw.githubusercontent.com/common-workflow-language/workflow-service/master/testdata/md5sum.cwl',
              'wdl':'https://raw.githubusercontent.com/common-workflow-language/workflow-service/master/testdata/md5sum.wdl',
              'py': 'https://raw.githubusercontent.com/common-workflow-language/workflow-service/master/test/test_integration.py',
              'unsupported': 'gs://topmed_workflow_testing/topmed_aligner/small_test_files_sbg/example_human_known_snp.py', # TODO: find real external file of .py, .cwl, .wdl
              'unreachable':'https://fake.py'}

    expected = {'cwl':('v1.0', 'CWL'),
                'wdl':('draft-2','WDL'),
                'py': ('2.7','PY'),
                'pyWithPrefix' : ('2.7','PY')}

    def testSupportedFormatChecking(self):
        """Check that non-wdl, -python, -cwl files are rejected."""

        # The choice to run this on local files prevents the irrelevant steps of creating and removing a new file.
        for format, location in self.local.items():
            if format != 'unsupported':
                # Tests the behavior after receiving supported file types with and without the 'file://' prefix
                self.assertEquals(wf_info(location), self.expected[format])
                self.assertEquals(wf_info(location[7:]), self.expected[format])

            else:
                # Tests behavior after recieveing a non supported file type.
                with self.assertRaises(TypeError):
                    wf_info(location)


    def testFileLocationChecking(self):
        """Check that the function rejects unsupported file locations."""
        # This needs to be run on remote files to get to the location checking step.
        for format, location in self.remote.items():
            if format == 'unsupported':
                # Tests behavior after receiving a non-existant file.
                with self.assertRaises(NotImplementedError):
                    wf_info(location)
            elif format == 'unreachable':
                # Tests behavior after receiving a non-existant file.
                with self.assertRaises(IOError):
                    wf_info(location)
            else:
                self.assertEquals(wf_info(location), self.expected[format])
                self.assertFalse(os.path.isfile(os.path.join(os.getcwd(), 'fetchedFromRemote.' + format)))
