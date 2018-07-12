from __future__ import absolute_import
import unittest
import time
import os
import subprocess32 as subprocess
import signal
import requests
import shutil


class ClientTest(unittest.TestCase):
    """A set of test cases for the wes-client."""
    def setUp(self):
        """Start a (local) wes-service server to make requests against."""
        self.wes_server_process = subprocess.Popen('python {}'.format(os.path.abspath('wes_service/wes_service_main.py')),
                                                   shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

    def test_dockstore_md5sum(self):
        """Fetch the md5sum cwl from dockstore, run it on the wes-service server, and check for the correct output."""
        output_filepath = run_md5sum(cwl_input='https://dockstore.org:8443/api/ga4gh/v2/tools/quay.io%2Fbriandoconnor%2Fdockstore-tool-md5sum/versions/master/plain-CWL/descriptor/%2FDockstore.cwl')

        self.assertTrue(check_for_file(output_filepath), 'Output file was not found: ' + str(output_filepath))
        shutil.rmtree('workflows')

    def test_local_md5sum(self):
        """Pass a local md5sum cwl to the wes-service server, and check for the correct output."""
        cwl_local_path = os.path.abspath('testdata/md5sum.cwl')
        output_filepath = run_md5sum(cwl_input='file://' + cwl_local_path)

        self.assertTrue(check_for_file(output_filepath), 'Output file was not found: ' + str(output_filepath))
        shutil.rmtree('workflows')


def run_md5sum(cwl_input):
    """Pass a local md5sum cwl to the wes-service server, and check for the correct output."""
    endpoint = 'http://localhost:8080/ga4gh/wes/v1/workflows'
    params = {'output_file': {'path': '/tmp/md5sum.txt', 'class': 'File'}, 'input_file': {'path': '../../testdata/md5sum.input', 'class': 'File'}}
    body = {'workflow_url': cwl_input, 'workflow_params': params, 'workflow_type': 'CWL', 'workflow_type_version': 'v1.0'}
    response = requests.post(endpoint, json=body).json()
    output_dir = os.path.abspath(os.path.join('workflows', response['workflow_id'], 'outdir'))
    return os.path.join(output_dir, 'md5sum.txt')


def get_server_pids():
    try:
        pids = subprocess.check_output(['pgrep', '-f', 'wes_service_main.py']).strip().split()
    except subprocess.CalledProcessError:
        return None
    return pids


def check_for_file(filepath, seconds=20):
    """Return True if a file exists within a certain amount of time."""
    if os.path.exists(filepath):
        return True
    else:
        wait_counter = 0
        while not os.path.exists(filepath):
            time.sleep(1)
            wait_counter += 1
            if os.path.exists(filepath):
                return True
            if wait_counter > seconds:
                return False


if __name__ == '__main__':
    unittest.main()  # run all tests
