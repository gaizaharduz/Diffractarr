## Build stage: compile pylibcue
FROM python:3.12-alpine AS build

RUN apk add --no-cache build-base bison flex && \
    pip install --no-cache-dir pylibcue && \
    mkdir /pylibcue && \
    cp -r /usr/local/lib/python3.12/site-packages/pylibcue* /pylibcue/

## Runtime
FROM python:3.12-alpine AS runtime

RUN apk add --no-cache ffmpeg flac

COPY --from=build /pylibcue/ /usr/local/lib/python3.12/site-packages/

RUN pip install --no-cache-dir signalrcore "chardet<6"

COPY src/diffractarr/ /app/diffractarr/

WORKDIR /app

## Test stage
FROM runtime AS test
RUN pip install --no-cache-dir pytest
COPY tests/ /app/tests/
ENV PYTHONPATH=/app
CMD ["pytest", "-v", "tests/"]

## Default: run the app
FROM runtime
CMD ["python3", "-m", "diffractarr"]
