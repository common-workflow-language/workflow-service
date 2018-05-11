# Workflow as a Service

This provides client and server implementations of the [GA4GH Workflow
Execution Service](https://github.com/ga4gh/workflow-execution-schemas) API for
the Common Workflow Language.

It provides an [Arvados](https://github.com/curoverse/arvados) backend.  It
also works with any `cwl-runner` that supports the CWL standard command line
interface: http://www.commonwl.org/v1.0/CommandLineTool.html#Executing_CWL_documents_as_scripts

## Installation:

```
pip install wes-service
```

## Usage

Run a standalone server with default `cwl-runner` backend:

```
$ wes-server
```

### Submit a workflow to run:

Note! All inputs files must be accessible from the filesystem.

```
$ wes-client --host=localhost:8080 testdata/md5sum.cwl testdata/md5sum.cwl.json
```

### List workflows

```
$ wes-client --proto http --host=locahost:8080 --list
```

### Get workflow status

```
$ wes-client --proto http --host=locahost:8080 --get <workflow-id>
```

### Get stderr log from workflow:

```
$ wes-client --proto http --host=locahost:8080 --log <workflow-id>
```

## Server Configuration

### Run a standalone server with Arvados backend:

```
$ wes-server --backend=wes_service.arvados_wes
```

### Use a different executable with cwl_runner backend

```
$ pip install toil
$ wes-server --backend=wes_service.cwl_runner --opt runner=cwltoil --opt extra=--logLevel=CRITICAL
```

### Pass parameters to cwl-runner

```
$ wes-server --backend=wes_service.cwl_runner --opt extra=--workDir=/
```

## Client Configuration

These options will be read in as defaults when running the client from the
command line. The default protocol is https, to support secure communications,
but the server starts using http, to ease development.

Set service endpoint:

```
$ export WES_API_HOST=localhost:8080
```

Set the value to pass in the `Authorization` header:

```
$ export WES_API_AUTH=my_api_token
```

Set the protocol (one of http, https)

```
$ export WES_API_PROTO=http
```

Then, when you call `wes-client` these defaults will be used in place of the
flags, `--host`, `--auth`, and `proto` respectively.
