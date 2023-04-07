"""The wx gridder!
  [o] "wawa"     Gridded NWS Watch Warning Advisory codes
  [o] "ptype"    Precip type (int flag) -> MRMS
  [o] "tmpc"     2m Air Temperature
  [o] "dwpc"     2m Dew Point
  [o] "smps"     10m Wind Speed
  [o] "drct"     10m Wind Direction (no u/v components)
  [o] "vsby"     Visibility, understanding that I can't go down below 1/8 mile
  [o] "roadtmpc" Pavement Temp, very crude regridding of RWIS data
  [o] "srad"     Solar Radiation (2014 onward)
  [o] "snwd"     Snow Depth would be once per day
  [o] "pcpn"     Precipitation
"""
import sys
import datetime
import os
import socket
import gzip
import tempfile

import pygrib
import numpy as np
import pytz
from pandas.io.sql import read_sql
from scipy.interpolate import NearestNDInterpolator
from geopandas import GeoDataFrame
from rasterio import features
from rasterio.transform import Affine
import boto3
from botocore.exceptions import ClientError
from pyiem import meteorology
from pyiem.datatypes import temperature, speed, distance, direction
from pyiem.network import Table as NetworkTable
from pyiem import reference
import pyiem.mrms as mrms_util
from pyiem.util import logger, get_dbconnstr

LOG = logger()
XAXIS = np.arange(reference.IA_WEST, reference.IA_EAST - 0.01, 0.01)
YAXIS = np.arange(reference.IA_SOUTH, reference.IA_NORTH - 0.01, 0.01)
XI, YI = np.meshgrid(XAXIS, YAXIS)
PROGRAM_VERSION = 0.8
DOMAIN = {
    "wawa": {"units": "1", "format": "%s"},
    "ptype": {"units": "1", "format": "%i"},
    "tmpc": {"units": "C", "format": "%.2f"},
    "dwpc": {"units": "C", "format": "%.2f"},
    "smps": {"units": "mps", "format": "%.1f"},
    "drct": {"units": "deg", "format": "%i"},
    "vsby": {"units": "km", "format": "%.3f"},
    "roadtmpc": {"units": "C", "format": "%.2f"},
    "srad": {"units": "Wm*{-2}", "format": "%.2f"},
    "snwd": {"units": "mm", "format": "%.2f"},
    "pcpn": {"units": "mm", "format": "%.2f"},
}
# This is not used at the moment
WWA_CODES = {
    "AS.Y": 5,  # Air Stagnation Advisory
    "EH.A": 6,  # Excessive Heat Watch
    "EC.W": 50,  # Extreme Cold Warning
    "FA.A": 51,  # Areal Flood Watch
    "EH.W": 52,  # Excessive Heat Warning
    "HT.Y": 53,  # Heat Advisory
    "FZ.W": 54,  # Freeze Warning
    "FR.Y": 55,  # Freeze Advisory
    "FW.A": 56,  # Fire Weather Watch
    "FW.W": 57,  # Fire Weather Warning
    "FZ.A": 58,  # Freeze Watch
    "HZ.W": 129,  # Hard Freeze Warning
    "WS.A": 130,  # Winter Storm Watch
    "BZ.A": 140,  # Blizzard Watch
    "SV.A": 145,  # Severe Thunderstorm Watch
    "TO.A": 146,  # Tornado Watch
    "FL.A": 147,  # Flood Watch
    "FL.S": 148,  # Flood Statement
    "WC.A": 149,  # Wind Chill Watch
    "FL.Y": 150,  # Flood Advisory
    "HW.A": 167,  # High Wind Watch
    "WC.W": 168,  # Wind Chill Warning
    "FL.W": 169,  # Flood Warning
    "BS.Y": 170,  # Blowing Snow Advisory
    "WI.Y": 171,  # Wind Advisory
    "WC.Y": 172,  # Wind Chill Advisory
    "FA.W": 173,  # Areal Flood Warning
    "FA.Y": 174,  # Areal Flood Advisory
    "FF.A": 175,  # Flas Flood Advisory
    "FF.W": 176,  # Flash Flood Warning
    "FG.Y": 177,  # Fog Advisory
    "HW.W": 224,  # High Wind Warning
    "SN.Y": 225,  # Snow Advisory
    "SB.Y": 226,  # Snow and Blowing Snow Advisory
    "WW.Y": 227,  # Winter Weather Advisory
    "SV.W": 228,  # Severe Thunderstorm Warning
    "HS.W": 229,  # Heavy Snow Warning
    "WS.W": 230,  # Winter Storm Warning
    "ZF.Y": 231,  # Freezing Fog Advisory
    "ZR.Y": 232,  # Freezing Rain Advisory
    "BZ.W": 240,  # Blizzard Warning
    "TO.W": 241,  # Tornado Warning
    "IS.W": 242,  # Ice Storm Warning
}


def upload_s3(fn):
    """Send file to S3 bucket."""
    session = boto3.Session(profile_name="ntrans")
    s3 = session.client("s3")
    sname = fn.split("/")[-1]
    LOG.info("Uploading %s to S3 as %s", fn, sname)
    try:
        # Does not return any metadata :/
        s3.upload_file(fn, "intrans-weather-feed", sname)
        return True
    except ClientError as e:
        LOG.error(e)
    return False


def write_grids(grids, valid, iarchive):
    """Do the write to disk"""
    fn = "/tmp/wx_%s.json" % (valid.strftime("%Y%m%d%H%M"),)
    out = open(fn, "w")
    out.write(
        """{"time": "%s",
    "type": "analysis",
    "revision": "%s",
    "hostname": "%s",
    "data": [
    """
        % (
            valid.strftime("%Y-%m-%dT%H:%M:%SZ"),
            PROGRAM_VERSION,
            socket.gethostname(),
        )
    )
    fmt = (
        '{"gid": %s, "tmpc": %.2f, "wawa": %s, "ptype": %i, "dwpc": %.2f, '
        '"smps": %.1f, "drct": %i, "vsby": %.3f, "roadtmpc": %.2f,'
        '"srad": %.2f, "snwd": %.2f, "pcpn": %.2f}'
    )
    i = 1
    ar = []
    for row in range(len(YAXIS)):
        for col in range(len(XAXIS)):
            a = grids["wawa"][row, col][:-1]
            ar.append(
                fmt
                % (
                    i,
                    grids["tmpc"][row, col],
                    repr(a.split(",")).replace("'", '"'),
                    grids["ptype"][row, col],
                    grids["dwpc"][row, col],
                    grids["smps"][row, col],
                    grids["drct"][row, col],
                    grids["vsby"][row, col],
                    grids["roadtmpc"][row, col],
                    grids["srad"][row, col],
                    grids["snwd"][row, col],
                    grids["pcpn"][row, col],
                )
            )
            i += 1
    out.write(",\n".join(ar))
    out.write("]}\n")
    out.close()
    if upload_s3(fn):
        os.unlink(fn)


def init_grids():
    """Create the grids, please"""
    grids = {}
    for label in DOMAIN:
        if label == "wawa":
            grids[label] = np.empty([324, 660], dtype="<U25")
        else:
            grids[label] = np.zeros((324, 660), np.float32)

    return grids


def transform_from_corner(ulx, uly, dx, dy):
    return Affine.translation(ulx, uly) * Affine.scale(dx, -dy)


def wwa(grids, valid, iarchive):
    """An attempt at rasterizing the WWA"""
    table = "warnings_%s" % (valid.year,)
    df = GeoDataFrame.from_postgis(
        """
        SELECT geom as geom, phenomena ||'.'|| significance as code, w.ugc from
        """
        + table
        + """ w JOIN ugcs u on (w.gid = u.gid) WHERE
        issue < %s and expire > %s
        and w.wfo in ('FSD', 'ARX', 'DVN', 'DMX', 'EAX', 'FSD', 'OAX', 'MPX')
    """,
        get_dbconnstr("postgis"),
        params=(valid, valid),
        index_col=None,
    )
    transform = transform_from_corner(
        reference.IA_WEST, reference.IA_NORTH, 0.01, 0.01
    )
    df["i"] = 1
    for vtec in df["code"].unique():
        df2 = df[df["code"] == vtec]
        shapes = ((geom, value) for geom, value in zip(df2.geometry, df2.i))
        stradd = "%s," % (vtec,)
        arr = features.rasterize(
            shapes=shapes,
            fill=0,
            transform=transform,
            out_shape=grids["wawa"].shape,
        )
        shp = grids["wawa"].shape
        for i in range(shp[0]):
            for j in range(shp[1]):
                if arr[i, j] > 0:
                    grids["wawa"][i, j] = grids["wawa"][i, j] + stradd


def snowd(grids, valid, iarchive):
    """Do the snowdepth grid"""
    df = read_sql(
        """
        SELECT ST_x(geom) as lon, ST_y(geom) as lat,
        max(snowd) as snow
        from summary s JOIN stations t on (s.iemid = t.iemid)
        WHERE s.day in (%s, %s) and
        t.network in ('IA_COOP', 'MN_COOP', 'WI_COOP', 'IL_COOP',
        'MO_COOP', 'NE_COOP', 'KS_COOP', 'SD_COOP') and snowd >= 0
        and snowd < 100 GROUP by lon, lat
        """,
        get_dbconnstr("iem"),
        params=(valid.date(), (valid - datetime.timedelta(days=1)).date()),
        index_col=None,
    )

    nn = NearestNDInterpolator(
        (df["lon"].values, df["lat"].values),
        distance(df["snow"].values, "IN").value("MM"),
    )
    grids["snwd"] = nn(XI, YI)


def roadtmpc(grids, valid, iarchive):
    """Do the RWIS Road times grid"""
    if iarchive:
        nt = NetworkTable(
            [
                "IA_RWIS",
                "MN_RWIS",
                "WI_RWIS",
                "IL_RWIS",
                "MO_RWIS",
                "KS_RWIS",
                "NE_RWIS",
                "SD_RWIS",
            ]
        )
        df = read_sql(
            """
            SELECT station, tfs0 as tsf0
            from alldata WHERE valid >= %s and valid < %s and
            tfs0 >= -50 and tfs0 < 150
            """,
            get_dbconnstr("rwis"),
            params=(
                (valid - datetime.timedelta(minutes=30)),
                (valid + datetime.timedelta(minutes=30)),
            ),
            index_col=None,
        )
        df["lat"] = df["station"].apply(
            lambda x: nt.sts.get(x, {}).get("lat", 0)
        )
        df["lon"] = df["station"].apply(
            lambda x: nt.sts.get(x, {}).get("lon", 0)
        )
    else:
        df = read_sql(
            """
            SELECT ST_x(geom) as lon, ST_y(geom) as lat,
            tsf0
            from current c JOIN stations t on (c.iemid = t.iemid)
            WHERE c.valid > now() - '2 hours'::interval and
            t.network in ('IA_RWIS', 'MN_RWIS', 'WI_RWIS', 'IL_RWIS',
            'MO_RWIS', 'KS_RWIS', 'NE_RWIS', 'SD_RWIS') and tsf0 >= -50
            and tsf0 < 150
            """,
            get_dbconnstr("iem"),
            index_col=None,
        )

    nn = NearestNDInterpolator(
        (df["lon"].values, df["lat"].values),
        temperature(df["tsf0"].values, "F").value("C"),
    )
    grids["roadtmpc"] = nn(XI, YI)


def srad(grids, valid, iarchive):
    """Solar Radiation (W m**-2)"""
    if iarchive:
        pgconn = get_dbconnstr("isuag")
        # We have to split based on if we are prior to 1 Jan 2014
        if valid.year < 2014:
            nt = NetworkTable("ISUAG")
            # c800 is kilo calorie per meter squared per hour
            df = read_sql(
                """
                SELECT station, c800 * 1.162 as srad
                from hourly
                WHERE valid >= %s and valid < %s and c800 >= 0
                """,
                pgconn,
                params=(
                    (valid - datetime.timedelta(minutes=30)),
                    (valid + datetime.timedelta(minutes=30)),
                ),
                index_col=None,
            )
        else:
            nt = NetworkTable("ISUSM")
            # Not fully certain on this unit, but it appears to be ok
            df = read_sql(
                """
                SELECT station, slrkj_tot_qc * 1000. / 3600. as srad
                from sm_hourly
                WHERE valid >= %s and valid < %s and slrkj_tot_qc >= 0
                """,
                pgconn,
                params=(
                    (valid - datetime.timedelta(minutes=30)),
                    (valid + datetime.timedelta(minutes=30)),
                ),
                index_col=None,
            )
        df["lat"] = df["station"].apply(
            lambda x: nt.sts.get(x, {}).get("lat", 0)
        )
        df["lon"] = df["station"].apply(
            lambda x: nt.sts.get(x, {}).get("lon", 0)
        )
    else:
        df = read_sql(
            """
            SELECT ST_x(geom) as lon, ST_y(geom) as lat,
            srad
            from current c JOIN stations t on (c.iemid = t.iemid)
            WHERE c.valid > now() - '2 hours'::interval and
            t.network in ('ISUSM') and srad >= 0 and srad != 'NaN'
            """,
            get_dbconnstr("iem"),
            index_col=None,
        )
    if len(df.index) < 5:
        print(
            (
                "i5gridder abort len(data): %s for %s iarchive: %s"
                % (len(df.index), valid, iarchive)
            )
        )
        sys.exit()

    nn = NearestNDInterpolator(
        (df["lon"].values, df["lat"].values), df["srad"].values
    )
    grids["srad"] = nn(XI, YI)


def simple(grids, valid, iarchive):
    """Simple gridder (stub for now)"""
    if iarchive:
        df = read_sql(
            """
            SELECT ST_x(geom) as lon, ST_y(geom) as lat,
            tmpf, dwpf, sknt, drct, vsby
            from alldata c JOIN stations t on
            (c.station = t.id)
            WHERE c.valid >= %s and c.valid < %s and
            t.network in ('IA_ASOS', 'AWOS', 'MN_ASOS', 'WI_ASOS', 'IL_ASOS',
            'MO_ASOS', 'NE_ASOS', 'KS_ASOS', 'SD_ASOS') and sknt is not null
            and drct is not null and tmpf is not null and dwpf is not null
            and vsby is not null
            """,
            get_dbconnstr("asos"),
            params=(
                (valid - datetime.timedelta(minutes=30)),
                (valid + datetime.timedelta(minutes=30)),
            ),
            index_col=None,
        )
    else:
        df = read_sql(
            """
            SELECT ST_x(geom) as lon, ST_y(geom) as lat,
            tmpf, dwpf, sknt, drct, vsby
            from current c JOIN stations t on (c.iemid = t.iemid)
            WHERE c.valid > now() - '1 hour'::interval and
            t.network in ('IA_ASOS', 'AWOS', 'MN_ASOS', 'WI_ASOS', 'IL_ASOS',
            'MO_ASOS', 'NE_ASOS', 'KS_ASOS', 'SD_ASOS') and sknt is not null
            and drct is not null and tmpf is not null and dwpf is not null
            and vsby is not null
            """,
            get_dbconnstr("iem"),
            index_col=None,
        )

    if len(df.index) < 5:
        print(
            (
                "i5gridder abort len(data): %s for %s iarchive: %s"
                % (len(df.index), valid, iarchive)
            )
        )
        sys.exit()

    nn = NearestNDInterpolator(
        (df["lon"].values, df["lat"].values),
        temperature(df["tmpf"].values, "F").value("C"),
    )
    grids["tmpc"] = nn(XI, YI)

    nn = NearestNDInterpolator(
        (df["lon"].values, df["lat"].values),
        temperature(df["dwpf"].values, "F").value("C"),
    )
    grids["dwpc"] = nn(XI, YI)

    nn = NearestNDInterpolator(
        (df["lon"].values, df["lat"].values),
        speed(df["sknt"].values, "KT").value("MPS"),
    )
    grids["smps"] = nn(XI, YI)

    u, v = meteorology.uv(
        speed(df["sknt"].values, "KT"), direction(df["drct"].values, "DEG")
    )
    nn = NearestNDInterpolator(
        (df["lon"].values, df["lat"].values), u.value("MPS")
    )
    ugrid = nn(XI, YI)
    nn = NearestNDInterpolator(
        (df["lon"].values, df["lat"].values), v.value("MPS")
    )
    vgrid = nn(XI, YI)
    drct = (
        meteorology.drct(
            speed(ugrid.ravel(), "MPS"), speed(vgrid.ravel(), "MPS")
        )
        .value("DEG")
        .astype("i")
    )
    grids["drct"] = np.reshape(drct, (len(YAXIS), len(XAXIS)))

    nn = NearestNDInterpolator(
        (df["lon"].values, df["lat"].values),
        distance(df["vsby"].values, "MI").value("KM"),
    )
    grids["vsby"] = nn(XI, YI)


def ptype(grids, valid, iarchive):
    """MRMS Precip Type
    http://www.nssl.noaa.gov/projects/mrms/operational/tables.php
    -3    no coverage
    0    no precipitation
    1    warm stratiform rain
    2    warm stratiform rain
    3    snow
    4    snow
    5    reserved for future use
    6    convective rain
    7    rain mixed with hail
    8    reserved for future use
    9    flag no longer used
    10    cold stratiform rain
    91    tropical/stratiform rain mix
    96    tropical/convective rain mix
    """
    floor = datetime.datetime(2016, 1, 21)
    floor = floor.replace(tzinfo=pytz.timezone("UTC"))
    if valid < floor:
        # Use hack for now
        grids["ptype"] = np.where(grids["tmpc"] < 0, 3, 10)
        return

    fn = None
    i = 0
    while i < 10:
        ts = valid - datetime.timedelta(minutes=i)
        if ts.minute % 2 == 0:
            testfn = mrms_util.fetch("PrecipFlag", ts, tmpdir="/tmp")
            if testfn is not None:
                fn = testfn
                break
        i += 1
    if fn is None:
        print("Warning, no PrecipFlag data found!")
        return

    fp = gzip.GzipFile(fn, "rb")
    (_, tmpfn) = tempfile.mkstemp()
    tmpfp = open(tmpfn, "wb")
    tmpfp.write(fp.read())
    tmpfp.close()
    grbs = pygrib.open(tmpfn)
    if grbs.messages < 1:
        print("i5gridder %s has %s messages?" % (tmpfn, grbs.messages))
        return
    grb = grbs[1]
    os.unlink(fn)
    os.unlink(tmpfn)

    # 3500, 7000, starts in upper left
    top = int((55.0 - reference.IA_NORTH) * 100.0)
    bottom = int((55.0 - reference.IA_SOUTH) * 100.0)

    right = int((reference.IA_EAST - -130.0) * 100.0) - 1
    left = int((reference.IA_WEST - -130.0) * 100.0)

    grids["ptype"] = np.flipud(grb["values"][top:bottom, left:right])


def pcpn(grids, valid, iarchive):
    """Attempt to use MRMS or stage IV pcpn here"""
    floor = datetime.datetime(2014, 11, 1)
    floor = floor.replace(tzinfo=pytz.timezone("UTC"))
    if valid < floor:
        # Use stageIV
        ts = (valid + datetime.timedelta(minutes=60)).replace(minute=0)
        gribfn = ts.strftime(
            ("/mesonet/ARCHIVE/data/%Y/%m/%d/stage4/ST4." "%Y%m%d%H.01h.grib")
        )
        if not os.path.isfile(gribfn):
            return
        grbs = pygrib.open(gribfn)
        grib = grbs[1]
        lats, lons = grib.latlons()
        vals = grib.values
        nn = NearestNDInterpolator(
            (lons.flatten(), lats.flatten()), vals.flatten()
        )
        grids["pcpn"] = nn(XI, YI)
        return
    fn = None
    i = 0
    while i < 10:
        ts = valid - datetime.timedelta(minutes=i)
        if ts.minute % 2 == 0:
            testfn = mrms_util.fetch("PrecipRate", ts, tmpdir="/tmp")
            if testfn is not None:
                fn = testfn
                break
        i += 1
    if fn is None:
        print("Warning, no PrecipRate data found!")
        return
    fp = gzip.GzipFile(fn, "rb")
    (_, tmpfn) = tempfile.mkstemp()
    tmpfp = open(tmpfn, "wb")
    tmpfp.write(fp.read())
    tmpfp.close()
    grbs = pygrib.open(tmpfn)
    values = grbs[1]["values"]
    # just set -3 (no coverage) to 0 for now
    values = np.where(values < 0, 0, values)
    os.unlink(fn)
    os.unlink(tmpfn)

    # 3500, 7000, starts in upper left
    top = int((55.0 - reference.IA_NORTH) * 100.0)
    bottom = int((55.0 - reference.IA_SOUTH) * 100.0)

    right = int((reference.IA_EAST - -130.0) * 100.0) - 1
    left = int((reference.IA_WEST - -130.0) * 100.0)

    # two minute accumulation is in mm/hr / 60 * 5
    # stage IV is mm/hr
    grids["pcpn"] = np.flipud(values[top:bottom, left:right]) / 12.0
    # print("i5gridder: min(pcpn) is %.2f" % (np.min(grids['pcpn']),))


def run(valid):
    """Run for this timestamp (UTC)"""
    grids = init_grids()
    floor = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
    floor = floor.replace(tzinfo=pytz.timezone("UTC"))
    iarchive = valid < floor
    simple(grids, valid, iarchive)
    wwa(grids, valid, iarchive)
    ptype(grids, valid, iarchive)
    pcpn(grids, valid, iarchive)
    snowd(grids, valid, iarchive)
    roadtmpc(grids, valid, iarchive)
    srad(grids, valid, iarchive)
    # [suspenders] Prevent negative numbers, unsure why we sometimes get these
    # from the data sources being used :/
    for vname in ["pcpn", "snwd", "srad"]:
        grids[vname] = np.where(grids[vname] >= 0, grids[vname], 0)
    write_grids(grids, valid, iarchive)


def main(argv):
    """Go Main Go"""
    if len(argv) != 6:
        print("Usage: python i5gridder.py YYYY mm dd HH MI")
        return
    valid = datetime.datetime(
        int(argv[1]), int(argv[2]), int(argv[3]), int(argv[4]), int(argv[5])
    )
    valid = valid.replace(tzinfo=pytz.timezone("UTC"))
    run(valid)


if __name__ == "__main__":
    main(sys.argv)


def test_upload():
    """Test our upload."""
    assert upload_s3("/tmp/wx_202107061940.json")
