from __future__ import absolute_import

import unittest
import time
import os
import subprocess32 as subprocess
import signal
import shutil
import logging
import sys

pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))  # noqa
sys.path.insert(0, pkg_root)  # noqa

from wes_client.util import WESClient

logging.basicConfig(level=logging.INFO)


class IntegrationTest(unittest.TestCase):
    """A baseclass that's inherited for use with different cwl backends."""
    @classmethod
    def setUpClass(cls):
        # cwl
        cls.cwl_dockstore_url = 'https://dockstore.org:8443/api/ga4gh/v2/tools/quay.io%2Fbriandoconnor%2Fdockstore-tool-md5sum/versions/master/plain-CWL/descriptor/%2FDockstore.cwl'
        cls.cwl_local_path = os.path.abspath('testdata/md5sum.cwl')
        cls.cwl_json_input = "file://" + os.path.abspath('testdata/md5sum.json')
        cls.cwl_attachments = ['file://' + os.path.abspath('testdata/md5sum.input'),
                               'file://' + os.path.abspath('testdata/dockstore-tool-md5sum.cwl')]
        # wdl
        cls.wdl_local_path = os.path.abspath('testdata/md5sum.wdl')
        cls.wdl_json_input = "file://" + os.path.abspath('testdata/md5sum.wdl.json')
        cls.wdl_attachments = ['file://' + os.path.abspath('testdata/md5sum.input')]

        # client for the swagger API methods
        cls.client = WESClient({'auth': {'Authorization': ''}, 'proto': 'http', 'host': 'localhost:8080'})

        # manual test (wdl only working locally atm)
        cls.manual = False

    def setUp(self):
        """Start a (local) wes-service server to make requests against."""
        raise NotImplementedError

    def tearDown(self):
        """Kill the wes-service server."""
        os.kill(self.wes_server_process.pid, signal.SIGTERM)
        while get_server_pids():
            for pid in get_server_pids():
                try:
                    os.kill(int(pid), signal.SIGKILL)
                    time.sleep(3)
                except OSError as e:
                    print(e)
        if os.path.exists('workflows'):
            shutil.rmtree('workflows')
        unittest.TestCase.tearDown(self)

    def test_dockstore_md5sum(self):
        """HTTP md5sum cwl (dockstore), run it on the wes-service server, and check for the correct output."""
        outfile_path, _ = self.run_md5sum(wf_input=self.cwl_dockstore_url,
                                          json_input=self.cwl_json_input,
                                          workflow_attachment=self.cwl_attachments)
        self.assertTrue(check_for_file(outfile_path), 'Output file was not found: ' + str(outfile_path))

    def test_local_md5sum(self):
        """LOCAL md5sum cwl to the wes-service server, and check for the correct output."""
        outfile_path, run_id = self.run_md5sum(wf_input=self.cwl_local_path,
                                               json_input=self.cwl_json_input,
                                               workflow_attachment=self.cwl_attachments)
        self.assertTrue(check_for_file(outfile_path), 'Output file was not found: ' + str(outfile_path))

    def test_run_attachments(self):
        """LOCAL md5sum cwl to the wes-service server, check for attachments."""
        outfile_path, run_id = self.run_md5sum(wf_input=self.cwl_local_path,
                                               json_input=self.cwl_json_input,
                                               workflow_attachment=self.cwl_attachments)
        get_response = self.client.get_run_log(run_id)["request"]
        self.assertTrue(check_for_file(outfile_path), 'Output file was not found: ' + get_response["workflow_attachment"])
        attachment_tool_path = get_response["workflow_attachment"][7:] + "/dockstore-tool-md5sum.cwl"
        self.assertTrue(check_for_file(attachment_tool_path), 'Attachment file was not found: ' + get_response["workflow_attachment"])

    def test_get_service_info(self):
        """
        Test wes_client.util.WESClient.get_service_info()

        This method will exit(1) if the response is not 200.
        """
        r = self.client.get_service_info()
        assert 'workflow_type_versions' in r
        assert 'supported_wes_versions' in r
        assert 'supported_filesystem_protocols' in r
        assert 'engine_versions' in r

    def test_list_runs(self):
        """
        Test wes_client.util.WESClient.list_runs()

        This method will exit(1) if the response is not 200.
        """
        r = self.client.list_runs()
        assert 'workflows' in r

    def test_get_run_status(self):
        """
        Test wes_client.util.WESClient.run_status()

        This method will exit(1) if the response is not 200.
        """
        outfile_path, run_id = self.run_md5sum(wf_input=self.cwl_local_path,
                                               json_input=self.cwl_json_input,
                                               workflow_attachment=self.cwl_attachments)
        r = self.client.get_run_status(run_id)
        assert 'state' in r
        assert 'run_id' in r

    def run_md5sum(self, wf_input, json_input, workflow_attachment=None):
        """Pass a local md5sum cwl to the wes-service server, and return the path of the output file that was created."""
        response = self.client.run(wf_input, json_input, workflow_attachment)
        assert 'run_id' in response, str(response.json())
        output_dir = os.path.abspath(os.path.join('workflows', response['run_id'], 'outdir'))
        return os.path.join(output_dir, 'md5sum.txt'), response['run_id']


def get_server_pids():
    try:
        pids = subprocess.check_output(['pgrep', '-f', 'wes_service_main.py']).strip().split()
    except subprocess.CalledProcessError:
        return None
    return pids


def check_for_file(filepath, seconds=120):
    """Return True if a file exists within a certain amount of time."""
    wait_counter = 0
    while not os.path.exists(filepath):
        time.sleep(1)
        wait_counter += 1
        if wait_counter > seconds:
            return False
    return True


class CwltoolTest(IntegrationTest):
    """Test using cwltool."""

    def setUp(self):
        """
        Start a (local) wes-service server to make requests against.
        Use cwltool as the wes-service server 'backend'.
        """
        self.wes_server_process = subprocess.Popen(
            'python {}'.format(os.path.abspath('wes_service/wes_service_main.py')),
            shell=True)
        time.sleep(5)


class ToilTest(IntegrationTest):
    """Test using Toil."""
    def setUp(self):
        """
        Start a (local) wes-service server to make requests against.
        Use toil as the wes-service server 'backend'.
        """
        self.wes_server_process = subprocess.Popen('python {} --backend=wes_service.toil_wes '
                                                   '--opt="extra=--logLevel=CRITICAL" '
                                                   '--opt="extra=--clean=never"'
                                                   ''.format(os.path.abspath('wes_service/wes_service_main.py')),
                                                   shell=True)
        time.sleep(5)

    def test_local_wdl(self):
        """LOCAL md5sum wdl to the wes-service server, and check for the correct output."""
        # Working locally but not on travis... >.<;
        if self.manual:
            outfile_path, run_id = self.run_md5sum(wf_input=self.wdl_local_path,
                                                   json_input=self.wdl_json_input,
                                                   workflow_attachment=self.wdl_attachments)
            self.assertTrue(check_for_file(outfile_path), 'Output file was not found: ' + str(outfile_path))


# Prevent pytest/unittest's discovery from attempting to discover the base test class.
del IntegrationTest


if __name__ == '__main__':
    unittest.main()  # run all tests
