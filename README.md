This is a proof of concept web service for the Common Workflow Language.  It
works with any `cwl-runner` that supports the CWL standard command line interface:
http://www.commonwl.org/draft-3/CommandLineTool.html#Executing_CWL_documents_as_scripts

Theory of operation:

* Accept job order via HTTP POST, create job and redirect to job URL
* Client can poll for job status
* Client can get streaming logs (stderr of `cwl-runner`)

Installation:

```
python setup.py install
```

Run standalone server:

```
cwl-server
```

Run a job, get status, get log:

```
$ echo '{"message": "It works"}' | curl -L -X POST -d@- http://localhost:5000/run?wf=https://raw.githubusercontent.com/common-workflow-language/common-workflow-language/master/draft-3/examples/1st-tool.cwl
{
    "state": "Running",
    "run": "https://raw.githubusercontent.com/common-workflow-language/common-workflow-language/master/draft-3/examples/1st-tool.cwl",
    "log": "http://localhost:5000/jobs/0/log",
    "input": {
        "message": "It works"
    },
    "output": null,
    "id": "http://localhost:5000/jobs/0"
}
$ curl http://localhost:5000/jobs/0
{
    "state": "Success",
    "run": "https://raw.githubusercontent.com/common-workflow-language/common-workflow-language/master/draft-3/examples/1st-tool.cwl",
    "log": "http://localhost:5000/jobs/0/log",
    "input": {
        "message": "It works"
    },
    "output": {},
    "id": "http://localhost:5000/jobs/0"
}
$ curl http://localhost:5000/jobs/0/log
cwl-runner 1.0.20160518201549
[job 1st-tool.cwl] /tmp/tmpKcoc_I$ echo \
    'It works'
It works
Final process status is success
```
