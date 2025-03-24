#!/bin/sh
set -ex
make dist
docker build --build-arg version=4.0 --build-arg arvversion=2.2.1 -t commonworkflowlanguage/workflow-service .
docker run -ti -p 127.0.0.1:3000:3000/tcp \
       -v$PWD/config.yml:/var/www/wes-server/config.yml \
       -v/etc/ssl/certs/ssl-cert-snakeoil.pem:/etc/ssl/certs/ssl-cert-wes.pem \
       -v/etc/ssl/private/ssl-cert-snakeoil.key:/etc/ssl/private/ssl-cert-wes.key \
       -v/var/run/docker.sock:/var/run/docker.sock \
       commonworkflowlanguage/workflow-service
