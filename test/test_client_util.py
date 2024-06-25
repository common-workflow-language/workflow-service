import logging
import os
import subprocess
import unittest

from wes_client.util import expand_globs, wf_info

logging.basicConfig(level=logging.INFO)

PRE = "https://raw.githubusercontent.com/common-workflow-language/workflow-service/main"


class IntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        dirname, filename = os.path.split(os.path.abspath(__file__))
        self.testdata_dir = dirname + "data"
        self.local = {
            "cwl": "file://" + os.path.join(os.getcwd() + "/testdata/md5sum.cwl"),
            "wdl": "file://" + os.path.join(os.getcwd() + "/testdata/md5sum.wdl"),
            "py": "file://" + os.path.join(os.getcwd() + "/test/test_integration.py"),
            "unsupported": "fake.txt",
        }

        self.remote = {
            "cwl": f"{PRE}/testdata/md5sum.cwl",
            "wdl": f"{PRE}/testdata/md5sum.wdl",
            "py": f"{PRE}/test/test_integration.py",
            "unsupported": "gs://topmed_workflow_testing/topmed_aligner/"
            "small_test_files_sbg/example_human_known_snp.py",
            "unreachable": "https://fake.py",
        }

        self.expected = {
            "cwl": ("v1.0", "CWL"),
            "wdl": ("draft-2", "WDL"),
            "py": ("3", "PY"),
            "pyWithPrefix": ("3", "PY"),
        }

    def tearDown(self) -> None:
        unittest.TestCase.tearDown(self)

    def test_expand_globs(self) -> None:
        """Asserts that wes_client.expand_globs() sees the same files in the cwd as 'ls'."""
        files = subprocess.check_output(["ls", "-1", "."])

        # python 2/3 bytestring/utf-8 compatibility
        if isinstance(files, str):
            files2 = files.split("\n")
        else:
            files2 = files.decode("utf-8").split("\n")

        if "" in files2:
            files2.remove("")
        files2 = ["file://" + os.path.abspath(f) for f in files2]
        glob_files = expand_globs("*")
        assert set(files2) == glob_files, (
            "\n" + str(set(files2)) + "\n" + str(glob_files)
        )

    def testSupportedFormatChecking(self) -> None:
        """
        Check that non-wdl, -python, -cwl files are rejected.

        This test is run only on local files to avoid downloading and removing a new file.
        """

        for file_format, location in self.local.items():
            if file_format != "unsupported":
                # Tests the behavior after receiving supported file types with
                # and without the 'file://' prefix
                self.assertEqual(wf_info(location), self.expected[file_format])
                self.assertEqual(wf_info(location[7:]), self.expected[file_format])

            else:
                # Tests behavior after receiving a non supported file type.
                with self.assertRaises(TypeError):
                    wf_info(location)

    def testFileLocationChecking(self) -> None:
        """
        Check that the function rejects unsupported file locations.

        This test needs to be run on remote files to test the location checking functionality of wf_info().
        """

        for file_format, location in self.remote.items():
            if file_format == "unsupported":
                # Tests behavior after receiving a file hosted at an unsupported location.
                with self.assertRaises(NotImplementedError):
                    wf_info(location)

            elif file_format == "unreachable":
                # Tests behavior after receiving a non-existent file.
                with self.assertRaises(IOError):
                    wf_info(location)

            else:
                self.assertEqual(wf_info(location), self.expected[file_format])
                self.assertFalse(
                    os.path.isfile(
                        os.path.join(os.getcwd(), "fetchedFromRemote." + file_format)
                    )
                )


if __name__ == "__main__":
    unittest.main()  # run all tests
