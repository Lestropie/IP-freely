FROM python:3.9
ARG DEBIAN_FRONTEND="noninteractive"

RUN pip3 install --upgrade pip && \
    pip3 install numpy

ENV PYTHONPATH="/ipfreely"

COPY ipfreely/ /ipfreely
COPY run.py /run.py
COPY version /version

ENTRYPOINT ["/run.py"]
