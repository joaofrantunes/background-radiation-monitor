FROM balenalib/raspberrypi3-debian-python:3.10-bookworm-build

WORKDIR /usr/app/src

# Upgrade pip and install virtualenv
RUN pip install --upgrade pip virtualenv

# Create and activate virtual environment
RUN virtualenv venv
ENV PATH="/usr/app/src/venv/bin:$PATH"

# Install only needed Python libraries (not GPIO ones!)
RUN pip install influxdb_client rpi-lgpio spidev lgpio

# Copy Python files
COPY *.py ./

# Run the script
CMD ["python", "counter.py"]
