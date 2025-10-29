FROM mcr.microsoft.com/devcontainers/base:jammy

RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y awscli && \
    apt-get install -y gdal-bin libgdal-dev && \
    apt-get clean -y && \
    rm -rf /var/lib/apt/lists/*   

COPY env.yaml /tmp/env.yaml