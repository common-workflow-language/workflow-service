import arvados
import arvados.util
import arvados.collection
import arvados.errors
import os
import connexion
import json
import subprocess
import tempfile
import functools
import threading
import logging
import shutil

from wes_service.util import visit, WESBackend


class MissingAuthorization(Exception):
    pass


def get_api(authtoken=None):
    if authtoken is None:
        if not connexion.request.headers.get('Authorization'):
            raise MissingAuthorization()
        authtoken = connexion.request.headers['Authorization']
        if not authtoken.startswith("Bearer ") or authtoken.startswith("OAuth2 "):
            raise ValueError("Authorization token must start with 'Bearer '")
        authtoken = authtoken[7:]
    return arvados.api_from_config(version="v1", apiconfig={
        "ARVADOS_API_HOST": os.environ["ARVADOS_API_HOST"],
        "ARVADOS_API_TOKEN": authtoken,
        "ARVADOS_API_HOST_INSECURE": os.environ.get("ARVADOS_API_HOST_INSECURE", "false"),  # NOQA
    })


statemap = {
    "Queued": "QUEUED",
    "Locked": "INITIALIZING",
    "Running": "RUNNING",
    "Complete": "COMPLETE",
    "Cancelled": "CANCELED"
}


def catch_exceptions(orig_func):
    """Catch uncaught exceptions and turn them into http errors"""

    @functools.wraps(orig_func)
    def catch_exceptions_wrapper(self, *args, **kwargs):
        try:
            return orig_func(self, *args, **kwargs)
        except arvados.errors.ApiError as e:
            logging.exception("Failure")
            return {"msg": e._get_reason(), "status_code": e.resp.status}, int(e.resp.status)
        except subprocess.CalledProcessError as e:
            return {"msg": str(e), "status_code": 500}, 500
        except MissingAuthorization:
            return {"msg": "'Authorization' header is missing or empty, expecting Arvados API token", "status_code": 401}, 401
        except ValueError as e:
            return {"msg": str(e), "status_code": 400}, 400
        except Exception as e:
            return {"msg": str(e), "status_code": 500}, 500

    return catch_exceptions_wrapper


class ArvadosBackend(WESBackend):
    def GetServiceInfo(self):
        stdout, stderr = subprocess.Popen(["arvados-cwl-runner", "--version"], stderr=subprocess.PIPE).communicate()
        return {
            "workflow_type_versions": {
                "CWL": {"workflow_type_version": ["v1.0"]}
            },
            "supported_wes_versions": ["0.3.0"],
            "supported_filesystem_protocols": ["http", "https", "keep"],
            "workflow_engine_versions": {
                "arvados-cwl-runner": stderr
            },
            "default_workflow_engine_parameters": [],
            "system_state_counts": {},
            "auth_instructions_url": "http://doc.arvados.org/user/reference/api-tokens.html",
            "tags": {
                "ARVADOS_API_HOST": os.environ["ARVADOS_API_HOST"]
            }
        }

    @catch_exceptions
    def ListRuns(self, page_size=None, page_token=None, state_search=None):
        api = get_api()

        paging = []
        if page_token:
            paging = [["uuid", ">", page_token]]

        requests = api.container_requests().list(
            filters=[["requesting_container_uuid", "=", None],
                     ["container_uuid", "!=", None]] + paging,
            select=["uuid", "command", "container_uuid"],
            order=["uuid"],
            limit=page_size).execute()["items"]
        containers = api.containers().list(
            filters=[["uuid", "in", [w["container_uuid"] for w in requests]]],
            select=["uuid", "state"]).execute()["items"]

        uuidmap = {c["uuid"]: statemap[c["state"]] for c in containers}

        workflow_list = [{"run_id": cr["uuid"],
                          "state": uuidmap.get(cr["container_uuid"])}
                         for cr in requests
                         if cr["command"] and cr["command"][0] == "arvados-cwl-runner"]
        return {
            "workflows": workflow_list,
            "next_page_token": workflow_list[-1]["run_id"] if workflow_list else ""
        }

    def log_for_run(self, run_id, message, authtoken=None):
        get_api(authtoken).logs().create(body={"log": {"object_uuid": run_id,
                                                       "event_type": "stderr",
                                                       "properties": {"text": message+"\n"}}}).execute()

    def invoke_cwl_runner(self, cr_uuid, workflow_url, workflow_params,
                          env, project_uuid,
                          tempdir):
        api = arvados.api_from_config(version="v1", apiconfig={
            "ARVADOS_API_HOST": env["ARVADOS_API_HOST"],
            "ARVADOS_API_TOKEN": env['ARVADOS_API_TOKEN'],
            "ARVADOS_API_HOST_INSECURE": env["ARVADOS_API_HOST_INSECURE"]  # NOQA
        })

        try:
            with tempfile.NamedTemporaryFile(dir=tempdir, suffix=".json") as inputtemp:
                json.dump(workflow_params, inputtemp)
                inputtemp.flush()

                msg = ""
                for dirpath, dirs, files in os.walk(tempdir):
                    for f in files:
                        msg += "  " + dirpath + "/" + f + "\n"

                self.log_for_run(cr_uuid, "Contents of %s:\n%s" % (tempdir, msg),
                                 env['ARVADOS_API_TOKEN'])

                # TODO: run submission process in a container to prevent
                # a-c-r submission processes from seeing each other.

                cmd = ["arvados-cwl-runner", "--submit-request-uuid="+cr_uuid,
                       "--submit", "--no-wait", "--api=containers"]

                if project_uuid:
                    cmd.append("--project-uuid="+project_uuid)

                cmd.append(workflow_url)
                cmd.append(inputtemp.name)

                self.log_for_run(cr_uuid, "Executing %s" % cmd, env['ARVADOS_API_TOKEN'])

                proc = subprocess.Popen(cmd, env=env,
                                        cwd=tempdir,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                (stdoutdata, stderrdata) = proc.communicate()
                if proc.returncode != 0:
                    api.container_requests().update(uuid=cr_uuid, body={"priority": 0}).execute()

                self.log_for_run(cr_uuid, stderrdata, env['ARVADOS_API_TOKEN'])

                if tempdir:
                    shutil.rmtree(tempdir)

        except subprocess.CalledProcessError as e:
            api.container_requests().update(uuid=cr_uuid, body={"priority": 0,
                                                                "properties": {"arvados-cwl-runner-log": str(e)}}).execute()

    @catch_exceptions
    def RunWorkflow(self, **args):
        if not connexion.request.headers.get('Authorization'):
            raise MissingAuthorization()

        authtoken = connexion.request.headers['Authorization']
        if authtoken.startswith("Bearer ") or authtoken.startswith("OAuth2 "):
            authtoken = authtoken[7:]

        env = {
            "PATH": os.environ["PATH"],
            "ARVADOS_API_HOST": os.environ["ARVADOS_API_HOST"],
            "ARVADOS_API_TOKEN": authtoken,
            "ARVADOS_API_HOST_INSECURE": os.environ.get("ARVADOS_API_HOST_INSECURE", "false")  # NOQA
        }

        api = get_api()

        cr = api.container_requests().create(body={"container_request":
                                                   {"command": [""],
                                                    "container_image": "n/a",
                                                    "state": "Uncommitted",
                                                    "output_path": "n/a",
                                                    "priority": 500}}).execute()

        try:
            tempdir, body = self.collect_attachments(cr["uuid"])

            workflow_url = body.get("workflow_url")

            project_uuid = body.get("workflow_engine_parameters", {}).get("project_uuid")

            threading.Thread(target=self.invoke_cwl_runner, args=(cr["uuid"],
                                                                  workflow_url,
                                                                  body["workflow_params"],
                                                                  env,
                                                                  project_uuid,
                                                                  tempdir)).start()

        except Exception as e:
            self.log_for_run(cr["uuid"], str(e))
            cr = api.container_requests().update(uuid=cr["uuid"],
                                                 body={"container_request":
                                                       {"priority": 0}}).execute()
        return {"run_id": cr["uuid"]}

    @catch_exceptions
    def GetRunLog(self, run_id):
        api = get_api()

        request = api.container_requests().get(uuid=run_id).execute()
        if request["container_uuid"]:
            container = api.containers().get(uuid=request["container_uuid"]).execute()  # NOQA
            task_reqs = arvados.util.list_all(api.container_requests().list, filters=[["requesting_container_uuid", "=", container["uuid"]]])
            tasks = arvados.util.list_all(api.containers().list, filters=[["uuid", "in", [tr["container_uuid"] for tr in task_reqs]]])
            containers_map = {c["uuid"]: c for c in tasks}
            containers_map[container["uuid"]] = container
        else:
            container = {
                "state": "Queued" if request["priority"] > 0 else "Cancelled",
                "exit_code": None,
                "log": None
            }
            tasks = []
            containers_map = {}
            task_reqs = []

        outputobj = {}
        if request["output_uuid"]:
            c = arvados.collection.CollectionReader(request["output_uuid"], api_client=api)
            with c.open("cwl.output.json") as f:
                try:
                    outputobj = json.load(f)
                except ValueError:
                    pass

                def keepref(d):
                    if isinstance(d, dict) and "location" in d:
                        d["location"] = "%sc=%s/_/%s" % (api._resourceDesc["keepWebServiceUrl"], c.portable_data_hash(), d["location"])  # NOQA

                visit(outputobj, keepref)

        def log_object(cr):
            if cr["container_uuid"]:
                containerlog = containers_map[cr["container_uuid"]]
            else:
                containerlog = {"started_at": "",
                                "finished_at": "",
                                "exit_code": None,
                                "log": ""}
            r = {
                "name": cr["name"] or "",
                "cmd": cr["command"],
                "start_time": containerlog["started_at"] or "",
                "end_time": containerlog["finished_at"] or "",
                "stdout": "",
                "stderr": "",
                "exit_code": containerlog["exit_code"] or 0
            }
            if containerlog["log"]:
                r["stdout"] = "%sc=%s/_/%s" % (api._resourceDesc["keepWebServiceUrl"], containerlog["log"], "stdout.txt")  # NOQA
                r["stderr"] = "%sc=%s/_/%s" % (api._resourceDesc["keepWebServiceUrl"], containerlog["log"], "stderr.txt")  # NOQA
            else:
                r["stdout"] = "%s/x-dynamic-logs/stdout" % (connexion.request.url)
                r["stderr"] = "%s/x-dynamic-logs/stderr" % (connexion.request.url)

            return r

        r = {
            "run_id": request["uuid"],
            "request": {
                "workflow_url": "",
                "workflow_params": request["mounts"].get("/var/lib/cwl/cwl.input.json", {}).get("content", {})
            },
            "state": statemap[container["state"]],
            "run_log": log_object(request),
            "task_logs": [log_object(t) for t in task_reqs],
            "outputs": outputobj
        }

        return r

    @catch_exceptions
    def CancelRun(self, run_id):  # NOQA
        api = get_api()
        request = api.container_requests().update(uuid=run_id, body={"priority": 0}).execute()  # NOQA
        return {"run_id": request["uuid"]}

    @catch_exceptions
    def GetRunStatus(self, run_id):
        api = get_api()
        request = api.container_requests().get(uuid=run_id).execute()
        if request["container_uuid"]:
            container = api.containers().get(uuid=request["container_uuid"]).execute()  # NOQA
        elif request["priority"] == 0:
            container = {"state": "Cancelled"}
        else:
            container = {"state": "Queued"}
        return {"run_id": request["uuid"],
                "state": statemap[container["state"]]}


def dynamic_logs(run_id, logstream):
    api = get_api()
    cr = api.container_requests().get(uuid=run_id).execute()
    l1 = [t["properties"]["text"]
          for t in api.logs().list(filters=[["object_uuid", "=", run_id],
                                            ["event_type", "=", logstream]],
                                   order="created_at desc",
                                   limit=100).execute()["items"]]
    if cr["container_uuid"]:
        l2 = [t["properties"]["text"]
              for t in api.logs().list(filters=[["object_uuid", "=", cr["container_uuid"]],
                                                ["event_type", "=", logstream]],
                                       order="created_at desc",
                                       limit=100).execute()["items"]]
    else:
        l2 = []
    return "".join(reversed(l1)) + "".join(reversed(l2))


def create_backend(app, opts):
    ab = ArvadosBackend(opts)
    app.app.route('/ga4gh/wes/v1/runs/<run_id>/x-dynamic-logs/<logstream>')(dynamic_logs)
    return ab
