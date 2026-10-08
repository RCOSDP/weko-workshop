# The COAR Notify inbox WEKO sends to, as a container to push to a registry.
#
# The docker-compose stack builds this same thing from source at "docker
# compose build"; a cluster wants an image instead, so build and push it
# once:
#
#     docker build -t <your registry>/weko3-inbox:pre .
#     docker push    <your registry>/weko3-inbox:pre
#
# Pin the branch to what the rest of the deployment is built from.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
WORKDIR $APP_HOME

FROM base AS production

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --branch nii_main https://github.com/RCOSDP/coar-notify-inbox.git $APP_HOME

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt --prefer-binary

EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
