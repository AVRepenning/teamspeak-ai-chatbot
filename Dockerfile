FROM python:3.12-alpine@sha256:4c47124a8391cb7a9f571164147d154777cf012a4ece5f86097130d7a4478111

WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.lock \
    && addgroup -S -g 10001 skynet \
    && adduser -S -D -H -u 10001 -G skynet skynet \
    && python -m pip uninstall -y pip
COPY skynet.py .
ENV HOME=/tmp
USER 10001:10001
CMD ["python", "-u", "skynet.py"]
