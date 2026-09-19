FROM balenalib/raspberrypi3-64-debian-python:3.10-bookworm-build

WORKDIR /usr/app/src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir influxdb_client rpi-lgpio

COPY *.py ./

CMD ["python", "counter.py"]
