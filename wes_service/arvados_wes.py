import arvados
import arvados.util
import arvados.collection
import os
import connexion
import json
import subprocess
import tempfile
from wes_service.util import visit, WESBackend


def get_api():
    return arvados.api_from_config(version="v1", apiconfig={
        "ARVADOS_API_HOST": os.environ["ARVADOS_API_HOST"],
        "ARVADOS_API_TOKEN": connexion.request.headers['Authorization'],
        "ARVADOS_API_HOST_INSECURE": os.environ.get("ARVADOS_API_HOST_INSECURE", "false"),  # NOQA
    })


statemap = {
    "Queued": "QUEUED",
    "Locked": "INITIALIZING",
    "Running": "RUNNING",
    "Complete": "COMPLETE",
    "Cancelled": "CANCELED"
}


class ArvadosBackend(WESBackend):
    def GetServiceInfo(self):
        return {
            "workflow_type_versions": {
                "CWL": {"workflow_type_version": ["v1.0"]}
            },
            "supported_wes_versions": "0.2.1",
            "supported_filesystem_protocols": ["file", "http", "https", "keep"],
            "engine_versions": "cwl-runner",
            "system_state_counts": {},
            "key_values": {}
        }

    def ListWorkflows(self):
        api = get_api()

        requests = arvados.util.list_all(api.container_requests().list,
                                         filters=[["requesting_container_uuid", "=", None],
                                                  ["container_uuid", "!=", None]],
                                         select=["uuid", "command", "container_uuid"])
        containers = arvados.util.list_all(api.containers().list,
                                           filters=[["uuid", "in", [w["container_uuid"] for w in requests]]],
                                           select=["uuid", "state"])

        uuidmap = {c["uuid"]: statemap[c["state"]] for c in containers}

        return {
            "workflows": [{"workflow_id": cr["uuid"],
                           "state": uuidmap.get(cr["container_uuid"])}
                          for cr in requests
                          if cr["command"] and cr["command"][0] == "arvados-cwl-runner"],
            "next_page_token": ""
        }

    def RunWorkflow(self, body):
        if body["workflow_type"] != "CWL" or body["workflow_type_version"] != "v1.0":  # NOQA
            return

        env = {
            "PATH": os.environ["PATH"],
            "ARVADOS_API_HOST": os.environ["ARVADOS_API_HOST"],
            "ARVADOS_API_TOKEN": connexion.request.headers['Authorization'],
            "ARVADOS_API_HOST_INSECURE": os.environ.get("ARVADOS_API_HOST_INSECURE", "false")  # NOQA
        }
        with tempfile.NamedTemporaryFile() as inputtemp:
            json.dump(body["workflow_params"], inputtemp)
            inputtemp.flush()
            workflow_id = subprocess.check_output(["arvados-cwl-runner", "--submit", "--no-wait", "--api=containers",  # NOQA
                                                   body.get("workflow_url"), inputtemp.name], env=env).strip()  # NOQA
        return {"workflow_id": workflow_id}

    def GetWorkflowLog(self, workflow_id):
        api = get_api()

        request = api.container_requests().get(uuid=workflow_id).execute()
        container = api.containers().get(uuid=request["container_uuid"]).execute()  # NOQA

        outputobj = {}
        if request["output_uuid"]:
            c = arvados.collection.CollectionReader(request["output_uuid"], api_client=api)
            with c.open("cwl.output.json") as f:
                outputobj = json.load(f)

                def keepref(d):
                    if isinstance(d, dict) and "location" in d:
                        d["location"] = "keep:%s/%s" % (c.portable_data_hash(), d["location"])  # NOQA

                visit(outputobj, keepref)

        stderr = ""
        if request["log_uuid"]:
            c = arvados.collection.CollectionReader(request["log_uuid"], api_client=api)
            if "stderr.txt" in c:
                with c.open("stderr.txt") as f:
                    stderr = f.read()

        r = {
            "workflow_id": request["uuid"],
            "request": {},
            "state": statemap[container["state"]],
            "workflow_log": {
                "cmd": [""],
                "startTime": "",
                "endTime": "",
                "stdout": "",
                "stderr": stderr
            },
            "task_logs": [],
            "outputs": outputobj
        }
        if container["exit_code"] is not None:
            r["workflow_log"]["exit_code"] = container["exit_code"]
        return r

    def CancelJob(self, workflow_id):  # NOQA
        api = get_api()
        request = api.container_requests().update(body={"priority": 0}).execute()  # NOQA
        return {"workflow_id": request["uuid"]}

    def GetWorkflowStatus(self, workflow_id):
        api = get_api()
        request = api.container_requests().get(uuid=workflow_id).execute()
        container = api.containers().get(uuid=request["container_uuid"]).execute()  # NOQA
        return {"workflow_id": request["uuid"],
                "state": statemap[container["state"]]}


def create_backend(opts):
    return ArvadosBackend(opts)
