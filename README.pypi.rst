Workflow as a Service
=====================

This provides client and server implementations of the `GA4GH Workflow
Execution
Service <https://github.com/ga4gh/workflow-execution-schemas>`__ API for
the Common Workflow Language.

It provides an `Arvados <https://github.com/curoverse/arvados>`__
backend. It also works with any ``cwl-runner`` that supports the CWL
standard command line interface:
http://www.commonwl.org/v1.0/CommandLineTool.html#Executing\_CWL\_documents\_as\_scripts

Installation:

::

    pip install wes-service

Run a standalone server with default ``cwl-runner`` backend:

::

    $ wes-server

Submit a workflow to run:

::

    $ wes-client --host=localhost:8080 myworkflow.cwl myjob.json

List workflows:

::

    $ wes-client --list

Get workflow status:

::

    $ wes-client --get <workflow-id>

Get stderr log from workflow:

::

    $ wes-client --log <workflow-id>

Server Options
==============

Run a standalone server with Arvados backend:
---------------------------------------------

::

    $ wes-server --backend=wes_service.arvados_wes

Use a different executable with cwl\_runner backend
---------------------------------------------------

::

    $ wes-server --backend=wes_service.cwl_runner --opt runner=cwltoil

Pass parameters to cwl-runner
-----------------------------

::

    $ wes-server --backend=wes_service.cwl_runner --opt extra=--workDir=/

Client environment options
==========================

Set service endpoint:

::

    $ export WES_API_HOST=localhost:8080

Set the value to pass in the ``Authorization`` header:

::

    $ export WES_API_AUTH=my_api_token

Set the protocol (one of http, https)

::

    $ export WES_API_PROTO=http
