FROM debian:9

# Package signing keys for Docker Engine and Phusion Passenger
ADD keys/58118E89F3A912897C070ADBF76221572C52609D.asc keys/561F9B9CAC40B2F7.asc /tmp/

# Install passenger

RUN apt-get update && \
    apt-get install -y dirmngr gnupg && \
    apt-key add --no-tty /tmp/561F9B9CAC40B2F7.asc && \
    apt-get install -y apt-transport-https ca-certificates && \
    sh -c 'echo deb https://oss-binaries.phusionpassenger.com/apt/passenger stretch main > /etc/apt/sources.list.d/passenger.list'

RUN apt-get update && \
    apt-get install -y --no-install-recommends passenger python-setuptools build-essential python-dev python-pip git && \
    pip install pip==9.0.3

RUN apt-get install -y --no-install-recommends libcurl4-openssl-dev libssl1.0-dev

RUN apt-key add --no-tty /tmp/58118E89F3A912897C070ADBF76221572C52609D.asc

RUN mkdir -p /etc/apt/sources.list.d && \
    echo deb https://apt.dockerproject.org/repo debian-stretch main > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get -yq --no-install-recommends install docker-engine=17.05.0~ce-0~debian-stretch && \
    apt-get clean

ARG arvversion
COPY dist/arvados-cwl-runner-${arvversion}.tar.gz /root
RUN cd /root && pip install arvados-cwl-runner-${arvversion}.tar.gz

ARG version
COPY dist/wes_service-${version}-*.whl /root
RUN cd /root && pip install $(ls wes_service-${version}-*.whl)[arvados]

COPY passenger_wsgi.py /var/www/wes-server/passenger_wsgi.py

WORKDIR /var/www/wes-server/
RUN chown www-data:www-data -R /var/www && adduser www-data docker

CMD ["passenger", "start", "--environment=production", "--user=www-data"]
