"""Generate forecast grids"""

import glob
import os
import socket
import sys
from datetime import datetime, timezone

import boto3
import numpy as np
import pygrib
import requests
from botocore.exceptions import ClientError
from pyiem import reference
from pyiem.datatypes import humidity, speed, temperature
from pyiem.meteorology import dewpoint, drct
from pyiem.reference import ISO8601
from pyiem.util import exponential_backoff, logger
from scipy.interpolate import NearestNDInterpolator

LOG = logger()
TMP = "/mesonet/tmp"
PROGRAM_VERSION = "2"
XAXIS = np.arange(reference.IA_WEST, reference.IA_EAST - 0.01, 0.01)
YAXIS = np.arange(reference.IA_SOUTH, reference.IA_NORTH - 0.01, 0.01)
XI, YI = np.meshgrid(XAXIS, YAXIS)
G = {"LATS": None, "LONS": None}


def dl(valid):
    for fhour in range(0, 85, 3):
        fn = "%s/%sF%03i.grib2" % (TMP, valid.strftime("%Y%m%d%H%M"), fhour)
        if os.path.isfile(fn):
            continue
        # Go Fetch it!
        uri = valid.strftime(
            (
                "http://mtarchive.geol.iastate.edu/%Y/%m/%d/"
                "grib2/ncep/NAM218/%H/%Y%m%d%H%MF"
                + ("%03i" % (fhour,))
                + ".grib2"
            )
        )
        r = exponential_backoff(requests.get, uri, timeout=60)
        if r is None or r.status_code != 200:
            print("fxgridder dl error for: %s" % (uri,))
            continue
        with open(fn, "wb") as o:
            o.write(r.content)


def write_grids(fp, valid, fhour):
    """Do the write to disk"""
    gribfn = "%s/%sF%03i.grib2" % (TMP, valid.strftime("%Y%m%d%H%M"), fhour)
    if not os.path.isfile(gribfn):
        print("Skipping write_grids because of missing fn: %s" % (gribfn,))
        return
    gribs = pygrib.open(gribfn)
    grids = dict()
    for grib in gribs:
        grids[grib.name] = grib
    d = dict()
    if "2 metre temperature" in grids:
        g = grids["2 metre temperature"]
        if G["LATS"] is None:
            G["LATS"], G["LONS"] = g.latlons()
        vals = temperature(g.values, "K").value("C")
        nn = NearestNDInterpolator(
            (G["LONS"].flatten(), G["LATS"].flatten()), vals.flatten()
        )
        d["tmpc"] = nn(XI, YI)
        if "2 metre relative humidity" in grids:
            g = grids["2 metre relative humidity"]
            vals = g.values
            nn = NearestNDInterpolator(
                (G["LONS"].flatten(), G["LATS"].flatten()), vals.flatten()
            )
            rh = nn(XI, YI)
            d["dwpc"] = dewpoint(
                temperature(d["tmpc"], "C"), humidity(rh, "%")
            ).value("C")
    if (
        "10 metre U wind component" in grids
        and "10 metre V wind component" in grids
    ):
        u = grids["10 metre U wind component"].values
        v = grids["10 metre V wind component"].values
        vals = ((u**2) + (v**2)) ** 0.5
        nn = NearestNDInterpolator(
            (G["LONS"].flatten(), G["LATS"].flatten()), vals.flatten()
        )
        d["smps"] = nn(XI, YI)
        vals = drct(speed(u, "MPS"), speed(v, "MPS")).value("deg")
        nn = NearestNDInterpolator(
            (G["LONS"].flatten(), G["LATS"].flatten()), vals.flatten()
        )
        d["drct"] = nn(XI, YI)
    if "Total Precipitation" in grids:
        vals = grids["Total Precipitation"].values
        nn = NearestNDInterpolator(
            (G["LONS"].flatten(), G["LATS"].flatten()), vals.flatten()
        )
        d["pcpn"] = nn(XI, YI)
    if "Visibility" in grids:
        vals = grids["Visibility"].values / 1000.0  # km
        nn = NearestNDInterpolator(
            (G["LONS"].flatten(), G["LATS"].flatten()), vals.flatten()
        )
        d["vsby"] = nn(XI, YI)

    fp.write(
        """{"forecast_hour": "%03i",
    "gids": [
"""
        % (fhour,)
    )
    fmt = (
        '{"gid": %s, "tmpc": %s, "dwpc": %s, '
        '"smps": %s, "drct": %s, "vsby": %s, "pcpn": %s}'
    )
    i = 1
    ar = []

    def f(label, row, col, fmt):
        if label not in d:
            return "null"
        return fmt % d[label][row, col]

    for row in range(len(YAXIS)):
        for col in range(len(XAXIS)):
            ar.append(
                fmt
                % (
                    i,
                    f("tmpc", row, col, "%.2f"),
                    f("dwpc", row, col, "%.2f"),
                    f("smps", row, col, "%.1f"),
                    f("drct", row, col, "%i"),
                    f("vsby", row, col, "%.3f"),
                    f("pcpn", row, col, "%.2f"),
                )
            )
            i += 1
    fp.write(",\n".join(ar))
    fp.write("]}%s\n" % ("," if fhour != 84 else "",))


def write_header(fp, valid):
    """Initialize the file"""
    fp.write(
        """{"Date": "%s",
        "model_init_time": "%s",
        "type": "forecast",
        "revision": "%s",
        "hostname": "%s",
        "data": [
    """
        % (
            valid.strftime("%Y-%m-%d"),
            valid.strftime(ISO8601),
            PROGRAM_VERSION,
            socket.gethostname(),
        )
    )


def write_footer(fp):
    fp.write("]}")


def upload_s3(fn):
    session = boto3.Session(profile_name="ntrans")
    s3 = session.client("s3")
    sname = fn.split("/")[-1]
    LOG.info("uploading %s to S3 as %s", fn, sname)
    try:
        # Does not return metadata :/
        s3.upload_file(fn, "intrans-weather-feed", sname)
        os.unlink(fn)
        return True
    except ClientError as e:
        LOG.error(e)
    return False


def cleanup(valid):
    files = glob.glob("%s/%sF???.grib2" % (TMP, valid.strftime("%Y%m%d%H%M")))
    for fn in files:
        os.unlink(fn)


def run(valid):
    """Do the work for this valid time"""
    # 1. Download NAM grib files from mtarchive
    dl(valid)
    # 2. create header
    fn = f"{TMP}/fx_{valid:%Y%n%d%H%M}.json"
    with open(fn, "w") as fp:
        write_header(fp, valid)
        # 3. write grids
        for fhour in range(0, 85, 3):
            write_grids(fp, valid, fhour)
        # 4. finalize file
        write_footer(fp)
    # 5. save to shared drive
    upload_s3(fn)
    # 6. cleanup cached gribs
    cleanup(valid)


def main(argv):
    if len(argv) != 5:
        print("Usage: python fxgridder.py YYYY mm dd HH")
        return
    valid = datetime(
        int(argv[1]),
        int(argv[2]),
        int(argv[3]),
        int(argv[4]),
        0,
        tzinfo=timezone.utc,
    )
    run(valid)


if __name__ == "__main__":
    main(sys.argv)
