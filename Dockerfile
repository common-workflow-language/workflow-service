FROM debian:9

# Install passenger

RUN apt-get update && \
    apt-get install -y dirmngr gnupg && \
    apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 561F9B9CAC40B2F7 && \
    apt-get install -y apt-transport-https ca-certificates && \
    sh -c 'echo deb https://oss-binaries.phusionpassenger.com/apt/passenger stretch main > /etc/apt/sources.list.d/passenger.list'

RUN apt-get update && \
    apt-get install -y passenger python-setuptools build-essential python-dev python-pip git && \
    pip install pip==9.0.3

RUN apt-get install -y libcurl4-openssl-dev libssl1.0-dev

ARG version

COPY dist/wes-service-${version}.tar.gz /root

RUN cd /root && tar xzf wes-service-${version}.tar.gz && \
    cd wes-service-${version} && \
    pip install .[arvados]

COPY passenger_wsgi.py /var/www/wes-server/passenger_wsgi.py

EXPOSE 443

WORKDIR /var/www/wes-server/
RUN chown www-data:www-data -R /var/www

CMD ["passenger", "start", "--environment=production", "--user=www-data", "--port=443", "--ssl", \
    "--ssl-certificate=/etc/ssl/certs/ssl-cert-wes.pem", \
    "--ssl-certificate-key=/etc/ssl/private/ssl-cert-wes.key"]
