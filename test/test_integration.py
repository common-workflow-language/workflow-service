from __future__ import absolute_import

import json
import unittest
import time
import os
import subprocess32 as subprocess
import signal
import requests
import shutil
import logging

from wes_client.util import build_wes_request

logging.basicConfig(level=logging.INFO)


class IntegrationTest(unittest.TestCase):
    """A baseclass that's inherited for use with different cwl backends."""
    @classmethod
    def setUpClass(cls):

        cls.cwl_dockstore_url = 'https://dockstore.org:8443/api/ga4gh/v2/tools/quay.io%2Fbriandoconnor%2Fdockstore-tool-md5sum/versions/master/plain-CWL/descriptor/%2FDockstore.cwl'
        cls.cwl_local_path = os.path.abspath('testdata/md5sum.cwl')
        cls.json_input = "file://" + os.path.abspath('testdata/md5sum.json')
        cls.attachments = ['file://' + os.path.abspath('testdata/md5sum.input'),
                           'file://' + os.path.abspath('testdata/dockstore-tool-md5sum.cwl')]

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
        # if os.path.exists('workflows'):
        #     shutil.rmtree('workflows')
        unittest.TestCase.tearDown(self)

    def test_dockstore_md5sum(self):
        """HTTP md5sum cwl (dockstore), run it on the wes-service server, and check for the correct output."""
        outfile_path, _ = run_cwl_md5sum(cwl_input=self.cwl_dockstore_url,
                                         json_input=self.json_input,
                                         workflow_attachment=self.attachments)
        self.assertTrue(check_for_file(outfile_path), 'Output file was not found: ' + str(outfile_path))

    def test_local_md5sum(self):
        """LOCAL md5sum cwl to the wes-service server, and check for the correct output."""
        outfile_path, run_id = run_cwl_md5sum(cwl_input=self.cwl_local_path,
                                              json_input=self.json_input,
                                              workflow_attachment=self.attachments)
        self.assertTrue(check_for_file(outfile_path), 'Output file was not found: ' + str(outfile_path))

    def test_multipart_upload(self):
        """LOCAL md5sum cwl to the wes-service server, and check for uploaded file in service."""
        outfile_path, run_id = run_cwl_md5sum(cwl_input=self.cwl_local_path,
                                              json_input=self.json_input,
                                              workflow_attachment=self.attachments)
        get_response = get_log_request(run_id)["request"]
        self.assertTrue(check_for_file(outfile_path), 'Output file was not found: ' + get_response["workflow_attachment"])
        self.assertTrue(check_for_file(get_response["workflow_url"][7:]), 'Output file was not found: ' + get_response["workflow_url"][:7])

    def test_run_attachments(self):
        """LOCAL md5sum cwl to the wes-service server, check for attachments."""
        outfile_path, run_id = run_cwl_md5sum(cwl_input=self.cwl_local_path,
                                              json_input=self.json_input,
                                              workflow_attachment=self.attachments)
        get_response = get_log_request(run_id)["request"]
        attachment_tool_path = get_response["workflow_attachment"][7:] + "/dockstore-tool-md5sum.cwl"
        self.assertTrue(check_for_file(outfile_path), 'Output file was not found: ' + get_response["workflow_attachment"])
        self.assertTrue(check_for_file(attachment_tool_path), 'Attachment file was not found: ' + get_response["workflow_attachment"])


def run_cwl_md5sum(cwl_input, json_input, workflow_attachment=None):
    """Pass a local md5sum cwl to the wes-service server, and return the path of the output file that was created."""
    endpoint = 'http://localhost:8080/ga4gh/wes/v1/runs'
    parts = build_wes_request(cwl_input,
                              json_input,
                              attachments=workflow_attachment)
    response = requests.post(endpoint, files=parts).json()
    assert 'run_id' in response, str(response.json())
    output_dir = os.path.abspath(os.path.join('workflows', response['run_id'], 'outdir'))
    return os.path.join(output_dir, 'md5sum.txt'), response['run_id']


def run_wdl_md5sum(wdl_input):
    """Pass a local md5sum wdl to the wes-service server, and return the path of the output file that was created."""
    endpoint = 'http://localhost:8080/ga4gh/wes/v1/runs'
    params = '{"ga4ghMd5.inputFile": "' + os.path.abspath('testdata/md5sum.input') + '"}'
    parts = [("workflow_params", params),
             ("workflow_type", "WDL"),
             ("workflow_type_version", "v1.0"),
             ("workflow_url", wdl_input)]
    response = requests.post(endpoint, files=parts).json()
    output_dir = os.path.abspath(os.path.join('workflows', response['workflow_id'], 'outdir'))
    check_travis_log = os.path.join(output_dir, 'stderr')
    with open(check_travis_log, 'r') as f:
        logging.info(f.read())
    logging.info(subprocess.check_output(['ls', os.path.join('workflows', response['workflow_id'])]))
    logging.info('\n')
    logging.info(subprocess.check_output(['ls', output_dir]))
    return os.path.join(output_dir, 'md5sum.txt'), response['workflow_id']


def get_log_request(run_id):
    endpoint = 'http://localhost:8080/ga4gh/wes/v1/runs/{}'.format(run_id)
    return requests.get(endpoint).json()


def get_server_pids():
    try:
        pids = subprocess.check_output(['pgrep', '-f', 'wes_service_main.py']).strip().split()
    except subprocess.CalledProcessError:
        return None
    return pids


def check_for_file(filepath, seconds=40):
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
        self.wes_server_process = subprocess.Popen('python {} --backend=wes_service.toil_wes --opt="extra=--logLevel=CRITICAL"'
                                                   ''.format(os.path.abspath('wes_service/wes_service_main.py')),
                                                   shell=True)
        time.sleep(5)


# Prevent pytest/unittest's discovery from attempting to discover the base test class.
del IntegrationTest

if __name__ == '__main__':
    unittest.main()  # run all tests
