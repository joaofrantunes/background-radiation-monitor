# Background Radiation Monitor

**A simple balenaCloud application to measure and record background radiation in your area. Radiation is detected with a cheaply available board, and connected to a Raspberry Pi to provide InfluxDB for datalogging and Grafana for pretty charts.**

![grafana-dashboard](https://raw.githubusercontent.com/balenalabs-incubator/background-radiation-monitor/master/assets/grafana-dashboard.png)

## Hardware required

* A Raspberry Pi (any model should be good for this, but I’d recommend a 3 or above just for performance reasons)
* An 8GB (or larger) SD card (we recommend SanDisk Extreme Pro SD cards)
* A power supply (PSU)
* A radiation detector [Amazon UK](https://www.amazon.co.uk/KKmoon-Assembled-Counter-Radiation-Detector/dp/B07S86Q5X8) or [AliExpress](https://www.aliexpress.com/item/32884861168.html?spm=a2g0o.productlist.0.0.5faf6aa9OuQXsc)
* Some [Dupont cables/jumper jerky](https://shop.pimoroni.com/products/jumper-jerky?variant=348491271) (you’ll need 3 female-female cables)


## Hardware connection

There are 3 connections we need to make from the radiation detector board to the Raspberry Pi. They are +5V and Ground (GND) for power, and the output pulse line to detect the count. Note that this is called `VIN` which can be a bit confusing as this usually means ‘voltage input’ or something similar, but on this board, it’s the output.

![pi-geiger-simple](https://raw.githubusercontent.com/balenalabs-incubator/background-radiation-monitor/master/assets/pi-geiger-simple.png)

In this configuration you only need to provide 5 volt power to one of the two boards; if you’re powering the Pi with a standard micro-USB power supply, that will power the detector board via the connections we’ve just made, as well.

## Software setup

Running this project is as simple as deploying it to a balenaCloud application, then downloading the OS image from the dashboard and flashing your SD card.

[![](https://balena.io/deploy.png)](https://dashboard.balena-cloud.com/deploy)

We recommend this button as the de-facto method for deploying new apps on balenaCloud, but as an alternative, you can set this project up with the repo and balenaCLI if you choose. Get the code from this repo, and set up [balenaCLI](https://github.com/balena-io/balena-cli) on your computer to push the code to balenaCloud and your devices. [Read more](https://www.balena.io/docs/learn/deploy/deployment/).


## J305 calibration and dose-rate estimate

The measured value produced directly by the detector is **CPM (counts per minute)**. The `usvh` field is an **estimated dose rate**, calculated as:

```text
estimated µSv/h = CPM × USVH_RATIO
```

For modern J305 glass tubes specified at **44 CPS per mR/h with Co-60**, the project now defaults to:

```text
USVH_RATIO=0.00332
```

That factor is derived from the 44 CPS/(mR/h) specification and the air-kerma conversion described in the J305 technical note below. The same note explains that the frequently copied legacy value `0.00812` corresponds to a different 18 CPS/(mR/h) assumption and should not automatically be applied to every J305 tube.

A J305-based monitoring study published in 2026 reports an operating range of **380–450 V** and used approximately **420 V** in the central plateau region. The same study also shows that uncompensated GM tubes have energy-dependent response and supports condition-specific calibration rather than one universal CPM-to-dose conversion factor. For that reason, CPM should be treated as the primary measurement and the µSv/h value as an estimate unless the complete detector has been calibrated against a suitable reference instrument under the intended radiation field.

The software keeps `USVH_RATIO` configurable so a measured calibration factor can replace the default without rebuilding the image. Each InfluxDB point also records `usvh_ratio` and `tube_model` as fields so the calibration context is retained with the data.

### Calibration references

- IoT-devices, **“Geiger tube J305: How to calculate the conversion factor of CPM to µSv/h”**: https://iot-devices.com.ua/en/geiger-tube-j305-how-to-calculate-the-conversion-factor-of-cpm-technical-note-en/
- Choi et al. (2026), **“Application of a low-cost Geiger–Müller monitoring system for clinical radiation environments”**, Journal of Applied Clinical Medical Physics: https://pmc.ncbi.nlm.nih.gov/articles/PMC13473700/
- InfluxData Python client documentation for synchronous writes: https://docs.influxdata.com/influxdb/cloud/api-guide/client-libraries/python/

## Access the dashboard

Once the software has been deployed and downloaded to your device, the dashboard will be accessible on the local IP address of the device, or via the balenaCloud public URL feature.

![public-url](https://raw.githubusercontent.com/balenalabs-incubator/background-radiation-monitor/master/assets/public-url.png)

## Raspberry Pi 3 64-bit / balenaCloud

The current release targets **Raspberry Pi 3 (using 64bit OS)** on balenaCloud.

Before deploying, configure the following balenaCloud **Service Variables**:

### influxdb service
- `DOCKER_INFLUXDB_INIT_PASSWORD`: choose a strong password.
- `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`: choose a long random token.

### counter service
- `INFLUX_TOKEN`: set this to the same value as `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`.
- `USVH_RATIO` (optional): conversion factor from CPM to estimated µSv/h. Defaults to `0.00332` for the modern J305 glass-tube specification discussed below.
- `GEIGER_TUBE_MODEL` (optional): tube model stored with each measurement. Defaults to `J305`.

### grafana service
- `INFLUX_TOKEN`: set this to the same value as `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`.

The token and password are intentionally not stored in this repository.

To deploy a new release with the balena CLI:

```sh
balena login
balena push g_jo_o_antunes/background-radiation-monitor
```

The `counter` container reads its InfluxDB connection settings from environment variables. Writes are synchronous, so a success message is printed only after InfluxDB accepts the write; transient failures are logged and the next measurement cycle attempts another write.

