FROM python:3.13-slim-bookworm AS requirements_builder

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    gcc \
    libssl-dev \
    libmariadb-dev \
    build-essential \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip setuptools

RUN pip install --no-cache-dir -r requirements.txt

RUN find . -type f -name "*.pyc" -delete


FROM python:3.13-slim-bookworm

ENV TZ=UTC \
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
    && rm -rf /var/lib/apt/lists/*

WORKDIR ${WORKDIR}

COPY --from=requirements_builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=requirements_builder /usr/local/bin /usr/local/bin

RUN git clone https://github.com/BsBlog/Sakura_embyboss .

ENTRYPOINT [ "python3" ]
CMD [ "main.py" ]
