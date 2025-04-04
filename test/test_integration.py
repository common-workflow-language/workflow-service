import logging
import os
import shutil
import signal
import subprocess
import time
import unittest
from typing import Optional, cast

import pytest
import requests

from wes_client.util import WESClient

logging.basicConfig(level=logging.INFO)


class IntegrationTest(unittest.TestCase):
    """A baseclass that's inherited for use with different cwl backends."""

    cwl_dockstore_url: str
    cwl_local_path: str
    cwl_json_input: str
    cwl_attachments: list[str]
    wdl_local_path: str
    wdl_json_input: str
    wdl_attachments: list[str]
    client: WESClient
    manual: bool
    wes_server_process: "subprocess.Popen[bytes]"

    @classmethod
    def setUpClass(cls) -> None:
        # cwl
        cls.cwl_dockstore_url = (
            "https://dockstore.org/api/ga4gh/trs/v2/tools/"
            "github.com%2Fmr-c%2Fdockstore-tool-md5sum/versions/"
            "master/PLAIN_CWL/descriptor//Dockstore.cwl"
        )
        cls.cwl_local_path = "file://" + os.path.abspath("testdata/md5sum.cwl")
        cls.cwl_json_input = "file://" + os.path.abspath("testdata/md5sum.json")
        cls.cwl_attachments = [
            "file://" + os.path.abspath("testdata/md5sum.input"),
            "file://" + os.path.abspath("testdata/dockstore-tool-md5sum.cwl"),
        ]
        # wdl
        cls.wdl_local_path = os.path.abspath("testdata/md5sum.wdl")
        cls.wdl_json_input = "file://" + os.path.abspath("testdata/md5sum.wdl.json")
        cls.wdl_attachments = ["file://" + os.path.abspath("testdata/md5sum.input")]

        # client for the swagger API methods
        cls.client = WESClient(
            {"auth": {"Authorization": ""}, "proto": "http", "host": "localhost:8080"}
        )

        # manual test (wdl only working locally atm)
        cls.manual = False

    def setUp(self) -> None:
        """Start a (local) wes-service server to make requests against."""
        raise NotImplementedError

    def tearDown(self) -> None:
        """Kill the wes-service server."""
        os.kill(self.wes_server_process.pid, signal.SIGTERM)
        pids = get_server_pids()
        while pids is not None:
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGKILL)
                    time.sleep(3)
                except OSError as e:
                    print(e)
            pids = get_server_pids()
        unittest.TestCase.tearDown(self)

    def test_dockstore_md5sum(self) -> None:
        """HTTP md5sum cwl (dockstore), run it on the wes-service server, and check for the correct output."""
        outfile_path, run_id = self.run_md5sum(
            wf_input=self.cwl_dockstore_url,
            json_input=self.cwl_json_input,
            workflow_attachment=self.cwl_attachments,
        )
        self.wait_for_finish(run_id)
        self.check_complete(run_id)
        self.assertTrue(
            self.check_for_file(outfile_path),
            "Output file was not found: " + str(outfile_path),
        )

    def test_local_md5sum(self) -> None:
        """LOCAL md5sum cwl to the wes-service server, and check for the correct output."""
        outfile_path, run_id = self.run_md5sum(
            wf_input=self.cwl_local_path,
            json_input=self.cwl_json_input,
            workflow_attachment=self.cwl_attachments,
        )
        self.wait_for_finish(run_id)
        self.check_complete(run_id)
        self.assertTrue(
            self.check_for_file(outfile_path),
            "Output file was not found: " + str(outfile_path),
        )

    # See https://ga4gh.github.io/workflow-execution-service-schemas/docs/#operation/GetRunLog
    @pytest.mark.skip(
        "workflow_attachment is not part of WES spec for the log.request body"
    )
    def test_run_attachments(self) -> None:
        """LOCAL md5sum cwl to the wes-service server, check for attachments."""
        outfile_path, run_id = self.run_md5sum(
            wf_input=self.cwl_local_path,
            json_input=self.cwl_json_input,
            workflow_attachment=self.cwl_attachments,
        )
        get_response = self.client.get_run_log(run_id)["request"]
        self.wait_for_finish(run_id)
        self.check_complete(run_id)
        self.assertTrue(
            self.check_for_file(outfile_path),
            "Output file was not found: " + get_response["workflow_attachment"],
        )
        attachment_tool_path = (
            get_response["workflow_attachment"][7:] + "/dockstore-tool-md5sum.cwl"
        )
        self.assertTrue(
            self.check_for_file(attachment_tool_path),
            "Attachment file was not found: " + get_response["workflow_attachment"],
        )

    def test_get_service_info(self) -> None:
        """
        Test wes_client.util.WESClient.get_service_info()

        This method will exit(1) if the response is not 200.
        """
        r = self.client.get_service_info()
        assert "workflow_type_versions" in r
        assert "supported_wes_versions" in r
        assert "supported_filesystem_protocols" in r
        assert "workflow_engine_versions" in r

    def test_list_runs(self) -> None:
        """
        Test wes_client.util.WESClient.list_runs()

        This method will exit(1) if the response is not 200.
        """
        r = self.client.list_runs()
        assert "workflows" in r

    def test_get_run_status(self) -> None:
        """
        Test wes_client.util.WESClient.run_status()

        This method will exit(1) if the response is not 200.
        """
        outfile_path, run_id = self.run_md5sum(
            wf_input=self.cwl_local_path,
            json_input=self.cwl_json_input,
            workflow_attachment=self.cwl_attachments,
        )
        r = self.client.get_run_status(run_id)
        assert "state" in r
        assert "run_id" in r

    def run_md5sum(
        self,
        wf_input: str,
        json_input: str,
        workflow_attachment: Optional[list[str]] = None,
    ) -> tuple[str, str]:
        """
        Pass a local md5sum cwl to the wes-service server.

        :return: the path of the output file that was created.
        """
        response = self.client.run(wf_input, json_input, workflow_attachment)
        assert "run_id" in response, str(response)
        output_dir = os.path.abspath(
            os.path.join("workflows", response["run_id"], "outdir")
        )
        return os.path.join(output_dir, "md5sum.txt"), response["run_id"]

    def wait_for_finish(self, run_id: str, seconds: int = 120) -> Optional[str]:
        """Return True if a file exists within a certain amount of time."""
        wait_counter = 0
        r = self.client.get_run_status(run_id)
        while r["state"] in ("QUEUED", "INITIALIZING", "RUNNING"):
            time.sleep(1)
            wait_counter += 1
            if wait_counter > seconds:
                return None
            r = self.client.get_run_status(run_id)
        return cast(str, r["state"])

    def check_complete(self, run_id: str) -> None:
        s = self.client.get_run_log(run_id)
        if s["state"] != "COMPLETE":
            logging.info(str(s["run_log"]["stderr"]))
            if str(s["run_log"]["stderr"]).startswith("http"):
                logs = requests.get(
                    s["run_log"]["stderr"], headers=self.client.auth
                ).text
                logging.info("Run log:\n" + logs)
        assert s["state"] == "COMPLETE"

    def check_for_file(self, filepath: str, seconds: int = 120) -> bool:
        """Return True if a file exists within a certain amount of time."""
        wait_counter = 0
        while not os.path.exists(filepath):
            time.sleep(1)
            wait_counter += 1
            if wait_counter > seconds:
                return False
        return True


def get_server_pids() -> Optional[list[bytes]]:
    try:
        pids = (
            subprocess.check_output(["pgrep", "-f", "wes_service_main.py"])
            .strip()
            .split()
        )
    except subprocess.CalledProcessError:
        return None
    return pids


class CwltoolTest(IntegrationTest):
    """Test using cwltool."""

    def setUp(self) -> None:
        """
        Start a (local) wes-service server to make requests against.
        Use cwltool as the wes-service server 'backend'.
        """
        if os.path.exists("workflows"):
            shutil.rmtree("workflows")
        self.wes_server_process = subprocess.Popen(
            [
                "python",
                os.path.abspath("wes_service/wes_service_main.py"),
                "--backend=wes_service.cwl_runner",
                "--opt",
                "runner=cwltool",
                "--port=8080",
            ]
        )
        time.sleep(5)


class ToilTest(IntegrationTest):
    """Test using Toil."""

    def setUp(self) -> None:
        """
        Start a (local) wes-service server to make requests against.
        Use toil as the wes-service server 'backend'.
        """
        self.wes_server_process = subprocess.Popen(
            "python {} --backend=wes_service.toil_wes "
            '--opt="extra=--logLevel=CRITICAL" '
            '--opt="extra=--clean=never"'
            "".format(os.path.abspath("wes_service/wes_service_main.py")),
            shell=True,
        )
        time.sleep(5)

    def test_local_wdl(self) -> None:
        """LOCAL md5sum wdl to the wes-service server, and check for the correct output."""
        # Working locally but not on travis... >.<;
        if self.manual:
            outfile_path, run_id = self.run_md5sum(
                wf_input=self.wdl_local_path,
                json_input=self.wdl_json_input,
                workflow_attachment=self.wdl_attachments,
            )
            self.assertTrue(
                self.check_for_file(outfile_path),
                "Output file was not found: " + str(outfile_path),
            )


@pytest.mark.skipif(
    not os.environ.get("ARVADOS_API_TOKEN"), reason="Arvados not configured"
)
class ArvadosTest(IntegrationTest):
    """Test using arvados-cwl-runner."""

    def setUp(self) -> None:
        """
        Start a (local) wes-service server to make requests against.
        Use arvados-cwl-runner as the wes-service server 'backend'.
        Requires ARVADOS_API_HOST and ARVADOS_API_TOKEN to be set in the environment.
        """
        if os.path.exists("workflows"):
            shutil.rmtree("workflows")
        self.wes_server_process = subprocess.Popen(
            [
                "python",
                os.path.abspath("wes_service/wes_service_main.py"),
                "--backend=wes_service.arvados_wes",
                "--port=8080",
            ]
        )
        self.client.auth = {
            "Authorization": "Bearer " + os.environ["ARVADOS_API_TOKEN"]
        }
        time.sleep(5)

    def check_for_file(self, filepath: str, seconds: int = 120) -> bool:
        # Doesn't make sense for arvados
        return True


# Prevent pytest/unittest's discovery from attempting to discover the base test class.
del IntegrationTest


if __name__ == "__main__":
    unittest.main()  # run all tests
