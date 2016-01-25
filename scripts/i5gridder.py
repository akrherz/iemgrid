"""The wx gridder!
  [o] "wawa"     Gridded NWS Watch Warning Advisory codes
  [o] "ptype"    Precip type (int flag) -> MRMS
  [o] "tmpc"     2m Air Temperature
  [o] "dwpc"     2m Dew Point
  [o] "smps"     10m Wind Speed
  [ ] "drct"     10m Wind Direction (no u/v components)
  [o] "vsby"     Visibility, understanding that I can't go down below 1/8 mile
  [ ] "roadtmpc" Pavement Temp, very crude regridding of RWIS data
  [ ] "srad"     Solar Radiation (2014 onward)
  [ ] "snwd"     Snow Depth would be once per day
  [o] "pcpn"     Precipitation
"""
import sys
import datetime
import pytz
import os
import socket
import shutil
import gzip
import pygrib
import tempfile
import zipfile
import numpy as np
from pyiem import reference
import psycopg2
from pandas.io.sql import read_sql
from scipy.interpolate import NearestNDInterpolator
from pyiem.datatypes import temperature, speed, distance
from geopandas import GeoDataFrame
from rasterio import features
from rasterio.transform import Affine


XAXIS = np.arange(reference.IA_WEST, reference.IA_EAST - 0.01, 0.01)
YAXIS = np.arange(reference.IA_SOUTH, reference.IA_NORTH - 0.01, 0.01)
XI, YI = np.meshgrid(XAXIS, YAXIS)
PROGRAM_VERSION = 0.2
DOMAIN = {'wawa': {'units': '1', 'format': '%s'},
          'ptype': {'units': '1', 'format': '%i'},
          'tmpc': {'units': 'C', 'format': '%.2f'},
          'dwpc': {'units': 'C', 'format': '%.2f'},
          'smps': {'units': 'mps', 'format': '%.1f'},
          'drct': {'units': 'deg', 'format': '%i'},
          'vsby': {'units': 'km', 'format': '%.3f'},
          'roadtmpc': {'units': 'C', 'format': '%.2f'},
          'srad': {'units': 'Wm*{-2}', 'format': '%.2f'},
          'snwd': {'units': 'mm', 'format': '%.2f'},
          'pcpn': {'units': 'mm', 'format': '%.2f'}
          }
# This is not used at the moment
WWA_CODES = {
 'AS.Y': 5,  # Air Stagnation Advisory
 'EH.A': 6,  # Excessive Heat Watch

 'EC.W': 50,  # Extreme Cold Warning
 'FA.A': 51,  # Areal Flood Watch
 'EH.W': 52,  # Excessive Heat Warning
 'HT.Y': 53,  # Heat Advisory
 'FZ.W': 54,  # Freeze Warning
 'FR.Y': 55,  # Freeze Advisory
 'FW.A': 56,  # Fire Weather Watch
 'FW.W': 57,  # Fire Weather Warning
 'FZ.A': 58,  # Freeze Watch

 'HZ.W': 129,  # Hard Freeze Warning
 'WS.A': 130,  # Winter Storm Watch
 'BZ.A': 140,  # Blizzard Watch
 'SV.A': 145,  # Severe Thunderstorm Watch
 'TO.A': 146,  # Tornado Watch
 'FL.A': 147,  # Flood Watch
 'FL.S': 148,  # Flood Statement
 'WC.A': 149,  # Wind Chill Watch
 'FL.Y': 150,  # Flood Advisory

 'HW.A': 167,  # High Wind Watch
 'WC.W': 168,  # Wind Chill Warning
 'FL.W': 169,  # Flood Warning
 'BS.Y': 170,  # Blowing Snow Advisory
 'WI.Y': 171,  # Wind Advisory
 'WC.Y': 172,  # Wind Chill Advisory
 'FA.W': 173,  # Areal Flood Warning
 'FA.Y': 174,  # Areal Flood Advisory
 'FF.A': 175,  # Flas Flood Advisory
 'FF.W': 176,  # Flash Flood Warning
 'FG.Y': 177,  # Fog Advisory

 'HW.W': 224,  # High Wind Warning
 'SN.Y': 225,  # Snow Advisory
 'SB.Y': 226,  # Snow and Blowing Snow Advisory
 'WW.Y': 227,  # Winter Weather Advisory
 'SV.W': 228,  # Severe Thunderstorm Warning
 'HS.W': 229,  # Heavy Snow Warning
 'WS.W': 230,  # Winter Storm Warning
 'ZF.Y': 231,  # Freezing Fog Advisory
 'ZR.Y': 232,  # Freezing Rain Advisory
 'BZ.W': 240,  # Blizzard Warning
 'TO.W': 241,  # Tornado Warning
 'IS.W': 242,  # Ice Storm Warning
 }


def write_grids(grids, valid):
    """Do the write to disk"""
    fns = []
    for label in grids:
        thisgrid = grids[label]
        fmt = '<cell gid="%s">' + DOMAIN[label]['format'] + '</cell>'
        fn = "/tmp/%s_%s.xml" % (label, valid.strftime("%Y%m%d%H%M"))
        fns.append(fn)
        out = open(fn, 'w')
        out.write("""<?xml version="1.0" encoding="UTF-8"?>
<wx>
<title>IEM Weather Grid</title>
<metadata>
  <time>%s</time>
  <revision>%s</revision>
  <hostname>%s</hostname>
</metadata>
<variable name="%s" units="%s" type="analysis" valid="%s">
""" % (valid.strftime("%Y-%m-%dT%H:%M:%SZ"), PROGRAM_VERSION,
                  socket.gethostname(), label, DOMAIN[label]['units'],
                  valid.strftime("%Y-%m-%dT%H:%M:%SZ")))
        i = 1
        for row in range(len(YAXIS)):
            for col in range(len(XAXIS)):
                out.write(fmt % (i, thisgrid[row, col]))
                i += 1
            out.write("\n")
        out.write("</variable></wx>")
        out.close()
    # Create a zipfile of this collection
    zipfn = "/tmp/wx_%s.zip" % (valid.strftime("%Y%m%d%H%M"), )
    z = zipfile.ZipFile(zipfn, 'w', zipfile.ZIP_DEFLATED)
    for fn in fns:
        z.write(fn, fn.split("/")[-1])
        os.unlink(fn)
    z.close()
    # move to cache folder
    shutil.copyfile(zipfn,
                    "/mesonet/share/pickup/ntrans/%s" % (
                        zipfn.split("/")[-1], ))
    os.unlink(zipfn)


def init_grids():
    """Create the grids, please"""
    grids = {}
    for label in DOMAIN:
        if label == 'wawa':
            grids[label] = np.chararray((324, 660))
            grids[label][:] = ''
        else:
            grids[label] = np.zeros((324, 660), np.float32)

    return grids


def transform_from_corner(ulx, uly, dx, dy):
    return Affine.translation(ulx, uly)*Affine.scale(dx, -dy)


def wwa(grids, valid):
    """An attempt at rasterizing the WWA"""
    pgconn = psycopg2.connect(database='postgis', host='iemdb', user='nobody')
    table = "warnings_%s" % (valid.year, )
    df = GeoDataFrame.from_postgis("""
        SELECT geom as geom, phenomena ||'.'|| significance as code, w.ugc from
        """ + table + """ w JOIN ugcs u on (w.gid = u.gid) WHERE
        issue < %s and expire > %s
        and w.wfo in ('FSD', 'ARX', 'DVN', 'DMX', 'EAX', 'FSD', 'OAX', 'MPX')
    """, pgconn, params=(valid, valid), index_col=None)
    transform = transform_from_corner(reference.IA_WEST, reference.IA_NORTH,
                                      0.01, 0.01)
    df['i'] = 1
    for vtec in df['code'].unique():
        df2 = df[df['code'] == vtec]
        shapes = ((geom, value) for geom, value in zip(df2.geometry, df2.i))
        stradd = "%s," % (vtec,)
        arr = features.rasterize(shapes=shapes, fill=0, transform=transform,
                                 out_shape=grids['wawa'].shape)
        shp = grids['wawa'].shape
        for i in range(shp[0]):
            for j in range(shp[1]):
                if arr[i, j] > 0:
                    grids['wawa'][i, j] = grids['wawa'][i, j] + stradd


def simple(grids, valid):
    """Simple gridder (stub for now)"""
    pgconn = psycopg2.connect(database='iem', host='iemdb', user='nobody')
    df = read_sql("""
        SELECT ST_x(geom) as lon, ST_y(geom) as lat,
        tmpf, dwpf, sknt, drct, vsby
        from current c JOIN stations t on (c.iemid = t.iemid)
        WHERE c.valid > now() - '1 hour'::interval and
        t.network in ('IA_ASOS', 'AWOS', 'MN_ASOS', 'WI_ASOS', 'IL_ASOS',
        'MO_ASOS', 'NE_ASOS', 'KS_ASOS', 'SD_ASOS')
        """, pgconn, index_col=None)

    nn = NearestNDInterpolator((df['lon'].values, df['lat'].values),
                               temperature(df['tmpf'].values, 'F').value('C'))
    grids['tmpc'] = nn(XI, YI)

    nn = NearestNDInterpolator((df['lon'].values, df['lat'].values),
                               temperature(df['dwpf'].values, 'F').value('C'))
    grids['dwpc'] = nn(XI, YI)

    nn = NearestNDInterpolator((df['lon'].values, df['lat'].values),
                               speed(df['sknt'].values, 'KT').value('MPS'))
    grids['smps'] = nn(XI, YI)

    nn = NearestNDInterpolator((df['lon'].values, df['lat'].values),
                               distance(df['vsby'].values, 'MI').value('KM'))
    grids['vsby'] = nn(XI, YI)


def ptype(grids, valid):
    """Attempt to use MRMS ptype here"""
    fn = None
    i = 0
    while i < 10:
        ts = valid - datetime.timedelta(minutes=i)
        testfn = ts.strftime(("/mnt/a4/data/%Y/%m/%d/mrms/ncep/PrecipFlag/"
                              "PrecipFlag_00.00_%Y%m%d-%H%M00.grib2.gz"))
        if os.path.isfile(testfn):
            fn = testfn
            break
        i += 1
    if fn is None:
        return

    fp = gzip.GzipFile(fn, 'rb')
    (_, tmpfn) = tempfile.mkstemp()
    tmpfp = open(tmpfn, 'wb')
    tmpfp.write(fp.read())
    tmpfp.close()
    grbs = pygrib.open(tmpfn)
    grb = grbs[1]
    os.unlink(tmpfn)

    # 3500, 7000, starts in upper left
    top = int((55. - reference.IA_NORTH) * 100.)
    bottom = int((55. - reference.IA_SOUTH) * 100.)

    right = int((reference.IA_EAST - -130.) * 100.) - 1
    left = int((reference.IA_WEST - -130.) * 100.)

    grids['ptype'] = np.flipud(grb['values'][top:bottom, left:right])


def pcpn(grids, valid):
    """Attempt to use MRMS pcpn here"""
    fn = None
    i = 0
    while i < 10:
        ts = valid - datetime.timedelta(minutes=i)
        testfn = ts.strftime(("/mnt/a4/data/%Y/%m/%d/mrms/ncep/PrecipRate/"
                              "PrecipRate_00.00_%Y%m%d-%H%M00.grib2.gz"))
        if os.path.isfile(testfn):
            fn = testfn
            break
        i += 1
    if fn is None:
        return
    fp = gzip.GzipFile(fn, 'rb')
    (_, tmpfn) = tempfile.mkstemp()
    tmpfp = open(tmpfn, 'wb')
    tmpfp.write(fp.read())
    tmpfp.close()
    grbs = pygrib.open(tmpfn)
    grb = grbs[1]
    os.unlink(tmpfn)

    # 3500, 7000, starts in upper left
    top = int((55. - reference.IA_NORTH) * 100.)
    bottom = int((55. - reference.IA_SOUTH) * 100.)

    right = int((reference.IA_EAST - -130.) * 100.) - 1
    left = int((reference.IA_WEST - -130.) * 100.)

    # two minute accumulation is in mm/hr / 60 * 5
    grids['pcpn'] = np.flipud(grb['values'][top:bottom, left:right]) * 12.0


def run(valid):
    """Run for this timestamp (UTC)"""
    grids = init_grids()
    simple(grids, valid)
    wwa(grids, valid)
    ptype(grids, valid)
    pcpn(grids, valid)
    write_grids(grids, valid)


def main(argv):
    """Go Main Go"""
    if len(argv) != 6:
        print("Usage: python i5gridder.py YYYY mm dd HH MI")
        return
    valid = datetime.datetime(int(argv[1]), int(argv[2]), int(argv[3]),
                              int(argv[4]), int(argv[5]))
    valid = valid.replace(tzinfo=pytz.timezone("UTC"))
    run(valid)

if __name__ == '__main__':
    main(sys.argv)
