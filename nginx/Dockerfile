FROM nginx:latest

# Install curl and download Consul-Template
RUN apt-get update && apt-get install -y curl unzip && \
    VERSION="0.39.0" && \
    curl -LO https://releases.hashicorp.com/consul-template/${VERSION}/consul-template_${VERSION}_linux_amd64.zip && \
    unzip consul-template_${VERSION}_linux_amd64.zip -d /usr/local/bin/ && \
    rm consul-template_${VERSION}_linux_amd64.zip && \
    apt-get purge -y curl unzip && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Expose HTTP and HTTPS ports
EXPOSE 80 443