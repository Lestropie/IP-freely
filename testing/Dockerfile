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

# Use the local worktree rather than cloning a fixed release tag, so that
# in-development source changes are exercised by the test suite.
# NOTE: this requires the build context to be the repository root, e.g.
#   docker build -f testing/Dockerfile -t ip-freely:testing .
COPY ipfreely /ipfreely/ipfreely
COPY run.py version requirements.txt /ipfreely/

WORKDIR /bids-examples
RUN git clone https://github.com/Lestropie/bids-examples . && \
    git checkout 344815a4b2cdaa93f2f77c1ab72c8a64cb904989
WORKDIR /

ENV PYTHONPATH="/ipfreely"

COPY testing/test_ipfreely.py /test_ipfreely.py
COPY testing/test_pybids.py /test_pybids.py
COPY testing/test_validators.py /test_validators.py
COPY testing/legacy_config.json /legacy_config.json
COPY testing/schema_config.json /schema_config.json

ENTRYPOINT ["python3", "/test_ipfreely.py", "/bids-examples"]
