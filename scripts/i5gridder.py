"""The wx gridder!
  [ ] "wawa"     Gridded NWS Watch Warning Advisory codes
  [ ] "ptype"    Precip type (int flag) -> MRMS
  [o] "tmpc"     2m Air Temperature
  [o] "dwpc"     2m Dew Point
  [o] "smps"     10m Wind Speed
  [ ] "drct"     10m Wind Direction (no u/v components)
  [o] "vsby"     Visibility, understanding that I can't go down below 1/8 mile
  [ ] "roadtmpc" Pavement Temp, very crude regridding of RWIS data
  [ ] "srad"     Solar Radiation (2014 onward)
  [ ] "snwd"     Snow Depth would be once per day
"""
import sys
import datetime
import pytz
import os
import socket
import shutil
import zipfile
import numpy as np
from pyiem import reference
import psycopg2
from pandas.io.sql import read_sql
from scipy.interpolate import NearestNDInterpolator
from pyiem.datatypes import temperature, speed, distance


XAXIS = np.arange(reference.IA_WEST, reference.IA_EAST - 0.01, 0.01)
YAXIS = np.arange(reference.IA_SOUTH, reference.IA_NORTH - 0.01, 0.01)
XI, YI = np.meshgrid(XAXIS, YAXIS)
PROGRAM_VERSION = 0.1
DOMAIN = {'wawa': {'units': '1', 'format': '%i'},
          'ptype': {'units': '1', 'format': '%i'},
          'tmpc': {'units': 'C', 'format': '%.2f'},
          'dwpc': {'units': 'C', 'format': '%.2f'},
          'smps': {'units': 'mps', 'format': '%.1f'},
          'drct': {'units': 'deg', 'format': '%i'},
          'vsby': {'units': 'km', 'format': '%.3f'},
          'roadtmpc': {'units': 'C', 'format': '%.2f'},
          'srad': {'units': 'Wm*{-2}', 'format': '%.2f'},
          'snwd': {'units': 'mm', 'format': '%.2f'}
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
        grids[label] = np.zeros((324, 660), np.float32)

    return grids


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


def run(valid):
    """Run for this timestamp (UTC)"""
    grids = init_grids()
    simple(grids, valid)
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
