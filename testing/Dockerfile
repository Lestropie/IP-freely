# TODO Unusual error with Python 3.9
FROM python:3.10
ARG DEBIAN_FRONTEND="noninteractive"

RUN apt-get update -yy && \
    apt-get install -y --no-install-recommends \
        git \
        nodejs \
        npm && \
    pip3 install \
        numpy==2.2.6 \
        pybids==0.19.0 && \
    npm install -gq \
        bids-validator@1.15.0 \
        deno@2.4.0 && \
    deno cache jsr:@bids/validator@2.0.7 && \
    rm -rf /var/apt/lists

# TODO Pulling tip of branch during initial development;
#   this will need to be tied to a commit hash once things are more stable
RUN git clone https://github.com/Lestropie/IP-Freely ipfreely --branch hackathon --depth 1

# TODO Pulling tip of branch during initial development;
#   this will need to be tied to a commit hash once things are more stable
WORKDIR /bids-examples
RUN git clone https://github.com/Lestropie/bids-examples . && \
    git checkout b378661e9fdb4985f45bd74d5931c7423a5263c3
WORKDIR /

ENV PYTHONPATH="/ipfreely"

COPY test_ipfreely.py /test_ipfreely.py
COPY test_validator.py /test_validator.py
COPY legacy_config.json /legacy_config.json
COPY schema_config.json /schema_config.json

ENTRYPOINT ["python3", "/test_ipfreely.py", "/bids-examples"]
