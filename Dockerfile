FROM debian:buster

# Package signing keys for Docker Engine and Phusion Passenger
ADD keys/58118E89F3A912897C070ADBF76221572C52609D.asc keys/561F9B9CAC40B2F7.asc keys/docker-archive-keyring.gpg /tmp/

# Install passenger

RUN apt-get update && \
    apt-get install -y dirmngr gnupg && \
    apt-key add --no-tty /tmp/561F9B9CAC40B2F7.asc && \
    apt-get install -y apt-transport-https ca-certificates && \
    sh -c 'echo deb https://oss-binaries.phusionpassenger.com/apt/passenger buster main > /etc/apt/sources.list.d/passenger.list'

RUN apt-get update && \
    apt-get install -y --no-install-recommends passenger python3-setuptools build-essential python3-dev python3-pip git && \
    pip3 install pip==21.1.3

RUN apt-get install -y --no-install-recommends libcurl4-openssl-dev libssl-dev

RUN mv /tmp/docker-archive-keyring.gpg /usr/share/keyrings/docker-archive-keyring.gpg
RUN mkdir -p /etc/apt/sources.list.d && \
    echo \
        "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian \
        buster stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get -yq --no-install-recommends install docker-ce=5:20.10.7~3-0~debian-buster docker-ce-cli containerd.io && \
    apt-get clean

ARG arvversion
COPY dist/arvados-cwl-runner-${arvversion}.tar.gz /root
RUN cd /root && pip3 install arvados-cwl-runner-${arvversion}.tar.gz

ARG version
COPY dist/wes_service-${version}-*.whl /root
RUN cd /root && pip3 install $(ls wes_service-${version}-*.whl)[arvados] connexion[swagger-ui]
COPY passenger_wsgi.py /var/www/wes-server/passenger_wsgi.py

WORKDIR /var/www/wes-server/
RUN chown www-data:www-data -R /var/www && adduser www-data docker

CMD ["passenger", "start", "--environment=production", "--user=www-data", "--python=python3"]
