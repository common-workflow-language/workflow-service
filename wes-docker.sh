#!/bin/sh
set -e
python setup.py sdist
docker build --build-arg version=2.3 -t commonworkflowlanguage/workflow-service .
docker run -ti \
       -v$PWD/config.yml:/var/www/wes-server/config.yml \
       -v/etc/ssl/certs/ssl-cert-snakeoil.pem:/etc/ssl/certs/ssl-cert-wes.pem \
       -v/etc/ssl/private/ssl-cert-snakeoil.key:/etc/ssl/private/ssl-cert-wes.key \
       -v/var/run/docker.sock:/var/run/docker.sock \
       commonworkflowlanguage/workflow-service
