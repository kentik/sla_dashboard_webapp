# syntax=docker/dockerfile:1
FROM python:3.9-slim

# install SLA dashboard app
WORKDIR /app
COPY domain domain
COPY infrastructure infrastructure
COPY presentation presentation
COPY routing.py routing.py
COPY generated generated
COPY main.py .
COPY requirements.txt .

# install build-essential needed by `pip3 install` on ARM64,
# then install python requirements,
# then uninstall build-essential to make the final image smaller;
# all commands are purposely in a single RUN statement,
# otherwise uninstalling build-essential would happen in a separate fs layer and resulting image would stay big
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential=12.9 && \
    pip3 install --no-cache-dir -r requirements.txt && \
    apt-get remove -y build-essential && \
    apt-get autoremove -y && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/*

# setup non-root user
ARG USER=sla-dashboard-user
RUN useradd --create-home ${USER}
USER ${USER}
ENV PATH=/home/${USER}/.local/bin:$PATH

CMD ["gunicorn", "--config=data/gunicorn.conf.py"]
