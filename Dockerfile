# FROM ghcr.io/bsblog/python-nogil:latest AS base_python
FROM python:3.13.8-slim AS base_python

FROM base_python AS requirements_builder

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    gcc \
    libssl-dev \
    libmariadb-dev \
    build-essential \
    curl \
    && apt-get clean \
    && apt-get dist-clean

COPY requirements.txt .

RUN pip install --upgrade pip setuptools

RUN pip install --no-cache-dir -r requirements.txt

RUN find . -type f -name "*.pyc" -delete


FROM base_python

ENV PYTHON_GIL=0 \
    TZ=UTC \
    DOCKER_MODE=1 \
    PYTHONUNBUFFERED=1 \
    WORKDIR=/app

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    ca-certificates \
    libmariadb3 \
    tzdata \
    git \
    default-mysql-client \
    && ln -snf /usr/share/zoneinfo/UTC /etc/localtime \
    && echo "UTC" > /etc/timezone \
    && apt-get clean \
    && apt-get autoremove -y \
    && apt-get dist-clean

WORKDIR ${WORKDIR}

# COPY --from=requirements_builder /usr/local/lib/python3.14t/site-packages /usr/local/lib/python3.14t/site-packages
COPY --from=requirements_builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=requirements_builder /usr/local/bin /usr/local/bin

RUN git clone https://github.com/BsBlog/Sakura_embyboss .

ENTRYPOINT ["python3","-X","gil=0"]
CMD [ "main.py" ]
