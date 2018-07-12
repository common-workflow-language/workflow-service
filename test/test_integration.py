from __future__ import absolute_import
from past.builtins import basestring
import unittest
import time
import os
import subprocess32 as subprocess
import signal
import requests


class ClientTest(unittest.TestCase):
    """A set of test cases for the wes-client."""
    def setUp(self):
        """Start a (local) wes-service server to make requests against."""
        self.wes_server_process = subprocess.Popen('python {} --debug'.format(os.path.abspath('wes_service/wes_service_main.py')), shell=True, stdout=subprocess.DEVNULL)
        time.sleep(5)

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
        unittest.TestCase.tearDown(self)

    def test_md5sum_response(self):
        output = '/tmp/md5sum.txt'
        endpoint = "http://localhost:8080/ga4gh/wes/v1/workflows"
        descriptor = "https://dockstore.org:8443/api/ga4gh/v2/tools/quay.io%2Fbriandoconnor%2Fdockstore-tool-md5sum/versions/master/plain-CWL/descriptor/%2FDockstore.cwl"
        params = {'output_file': {'path': output, 'class': 'File'}, 'input_file': {'path': '/home/ubuntu/mock_wes/workflow-service/testdata/md5sum.input', 'class': 'File'}}
        body = {"workflow_url":descriptor, "workflow_params": params, "workflow_type": "CWL", "workflow_type_version": "v1.0"}
        response = requests.post(endpoint, json=body).json()
        self.assertNotEqual(response['workflow_id'], None, msg='response["workflow_id"] returned a value of None instead of an ID.')
        self.assertTrue(isinstance(response['workflow_id'], basestring), msg='response["workflow_id"] returned a non-string value: ' + str(response["workflow_id"]))


def get_server_pids():
    try:
        pids = subprocess.check_output(['pgrep', '-f', 'wes_service_main.py']).strip().split()
    except subprocess.CalledProcessError:
        return None
    return pids

if __name__ == "__main__":
    unittest.main()  # run all tests
