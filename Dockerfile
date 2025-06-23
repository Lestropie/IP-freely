FROM python:3.9-slim

ARG DEBIAN_FRONTEND="noninteractive"

ENV PYTHONPATH="/ipfreely"

COPY ipfreely/ /ipfreely
COPY run.py /run.py
COPY version /version

ENTRYPOINT ["/run.py"]
