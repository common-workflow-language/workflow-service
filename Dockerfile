FROM debian:9

# Install passenger

RUN apt-get update && \
    apt-get install -y dirmngr gnupg && \
    apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 561F9B9CAC40B2F7 && \
    apt-get install -y apt-transport-https ca-certificates && \
    sh -c 'echo deb https://oss-binaries.phusionpassenger.com/apt/passenger stretch main > /etc/apt/sources.list.d/passenger.list'

RUN apt-get update && \
    apt-get install -y --no-install-recommends passenger python-setuptools build-essential python-dev python-pip git && \
    pip install pip==9.0.3

RUN apt-get install -y --no-install-recommends libcurl4-openssl-dev libssl1.0-dev

RUN apt-key adv --keyserver hkp://pool.sks-keyservers.net:80 --recv-keys 58118E89F3A912897C070ADBF76221572C52609D || \
    apt-key adv --keyserver hkp://pgp.mit.edu:80 --recv-keys 58118E89F3A912897C070ADBF76221572C52609D

RUN mkdir -p /etc/apt/sources.list.d && \
    echo deb https://apt.dockerproject.org/repo debian-stretch main > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get -yq --no-install-recommends install docker-engine=17.05.0~ce-0~debian-stretch && \
    apt-get clean

ARG arvversion
COPY dist/arvados-cwl-runner-${arvversion}.tar.gz /root
RUN cd /root && tar xzf arvados-cwl-runner-${arvversion}.tar.gz && \
    cd arvados-cwl-runner-${arvversion} && \
    pip install .

ARG version
COPY dist/wes-service-${version}.tar.gz /root
RUN cd /root && tar xzf wes-service-${version}.tar.gz && \
    cd wes-service-${version} && \
    pip install .[arvados]

COPY passenger_wsgi.py /var/www/wes-server/passenger_wsgi.py

WORKDIR /var/www/wes-server/
RUN chown www-data:www-data -R /var/www && adduser www-data docker

CMD ["passenger", "start", "--environment=production", "--user=www-data"]
