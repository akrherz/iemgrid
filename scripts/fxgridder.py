"""Generate forecast grids"""
import sys
import datetime
import pytz
import requests
import os
import pygrib
import socket
import shutil
import zipfile
import glob
import numpy as np
from scipy.interpolate import NearestNDInterpolator
from pyiem import reference
from pyiem.datatypes import temperature, humidity, speed
from pyiem.meteorology import dewpoint, drct

TMP = "/mesonet/tmp"
PROGRAM_VERSION = "1"
XAXIS = np.arange(reference.IA_WEST, reference.IA_EAST - 0.01, 0.01)
YAXIS = np.arange(reference.IA_SOUTH, reference.IA_NORTH - 0.01, 0.01)
XI, YI = np.meshgrid(XAXIS, YAXIS)
G = {'LATS': None, 'LONS': None}


def dl(valid):
    for fhour in range(0, 85, 3):
        fn = "%s/%sF%03i.grib2" % (TMP, valid.strftime("%Y%m%d%H%M"), fhour)
        if os.path.isfile(fn):
            continue
        # Go Fetch it!
        uri = valid.strftime(("http://mtarchive.geol.iastate.edu/%Y/%m/%d/"
                              "grib2/ncep/NAM218/%H/%Y%m%d%H%MF" +
                              ("%03i" % (fhour,)) + ".grib2"))
        r = requests.get(uri)
        if r.status_code != 200:
            print("fxgridder dl error for: %s" % (uri,))
            continue
        o = open(fn, 'wb')
        o.write(r.content)
        o.close()


def write_grids(valid, fhour):
    """Do the write to disk"""
    gribfn = "%s/%sF%03i.grib2" % (TMP, valid.strftime("%Y%m%d%H%M"),
                                   fhour)
    if not os.path.isfile(gribfn):
        print("Skipping write_grids because of missing fn: %s" % (gribfn,))
        return
    gribs = pygrib.open(gribfn)
    grids = dict()
    for grib in gribs:
        grids[grib.name] = grib
    d = dict()
    if '2 metre temperature' in grids:
        g = grids['2 metre temperature']
        if G['LATS'] is None:
            G['LATS'], G['LONS'] = g.latlons()
        vals = temperature(g.values, 'K').value('C')
        nn = NearestNDInterpolator((G['LONS'].flatten(), G['LATS'].flatten()),
                                   vals.flatten())
        d['tmpc'] = nn(XI, YI)
        if 'Relative humidity' in grids:
            g = grids['Relative humidity']
            vals = g.values
            nn = NearestNDInterpolator((G['LONS'].flatten(),
                                        G['LATS'].flatten()),
                                       vals.flatten())
            rh = nn(XI, YI)
            d['dwpc'] = dewpoint(temperature(d['tmpc'], 'C'),
                                 humidity(rh, '%')).value('C')
    if ('10 metre U wind component' in grids and
            '10 metre V wind component' in grids):
        u = grids['10 metre U wind component'].values
        v = grids['10 metre V wind component'].values
        vals = ((u ** 2) + (v ** 2)) ** 0.5
        nn = NearestNDInterpolator((G['LONS'].flatten(), G['LATS'].flatten()),
                                   vals.flatten())
        d['smps'] = nn(XI, YI)
        vals = drct(speed(u, 'MPS'), speed(v, 'MPS')).value('deg')
        nn = NearestNDInterpolator((G['LONS'].flatten(), G['LATS'].flatten()),
                                   vals.flatten())
        d['drct'] = nn(XI, YI)
    if 'Total Precipitation' in grids:
        vals = grids['Total Precipitation'].values
        nn = NearestNDInterpolator((G['LONS'].flatten(), G['LATS'].flatten()),
                                   vals.flatten())
        d['pcpn'] = nn(XI, YI)
    if 'Visibility' in grids:
        vals = grids['Visibility'].values / 1000.  # km
        nn = NearestNDInterpolator((G['LONS'].flatten(), G['LATS'].flatten()),
                                   vals.flatten())
        d['vsby'] = nn(XI, YI)

    fts = valid + datetime.timedelta(hours=fhour)
    fn = "%s/%sF%03i.json" % (TMP, valid.strftime("%Y%m%d%H%M"), fhour)
    out = open(fn, 'w')
    out.write("""{"time": "%s",
    "model_init_time": "%s",
    "forecast_hour": %s,
    "type": "forecast",
    "revision": "%s",
    "hostname": "%s",
    "data": [
    """ % (fts.strftime("%Y-%m-%dT%H:%M:%SZ"),
           valid.strftime("%Y-%m-%dT%H:%M:%SZ"), fhour,
           PROGRAM_VERSION, socket.gethostname()))
    fmt = ('{"gid": %s, "tmpc": %s, "dwpc": %s, '
           '"smps": %s, "drct": %s, "vsby": %s, "pcpn": %s}')
    i = 1
    ar = []

    def f(label, row, col, fmt):
        if label not in d:
            return 'null'
        return fmt % d[label][row, col]

    for row in range(len(YAXIS)):
        for col in range(len(XAXIS)):
            ar.append(fmt % (i, f('tmpc', row, col, '%.2f'),
                             f('dwpc', row, col, '%.2f'),
                             f('smps', row, col, '%.1f'),
                             f('drct', row, col, '%i'),
                             f('vsby', row, col, '%.3f'),
                             f('pcpn', row, col, '%.2f')))
            i += 1
    out.write(",\n".join(ar))
    out.write("]}\n")
    out.close()


def zipfiles(valid):
    files = glob.glob("%s/%sF???.json" % (TMP, valid.strftime("%Y%m%d%H%M")))
    # Create a zipfile of this collection
    zipfn = "%s/fx_%s.zip" % (TMP, valid.strftime("%Y%m%d%H%M"))
    z = zipfile.ZipFile(zipfn, 'w', zipfile.ZIP_DEFLATED)
    for fn in files:
        z.write(fn, fn.split("/")[-1])
        os.unlink(fn)
    z.close()
    # move to cache folder
    shutil.copyfile(zipfn,
                    "/mesonet/share/pickup/ntrans/%s" % (
                        zipfn.split("/")[-1], ))
    os.unlink(zipfn)


def cleanup(valid):
    files = glob.glob("%s/%sF???.grib2" % (TMP, valid.strftime("%Y%m%d%H%M")))
    for fn in files:
        os.unlink(fn)


def run(valid):
    """Do the work for this valid time"""
    # 1. Download NAM grib files from mtarchive
    dl(valid)
    # 2. write grids
    for fhour in range(0, 85, 3):
        write_grids(valid, fhour)
    # 3. save to shared drive
    zipfiles(valid)
    # 4. cleanup cached gribs
    cleanup(valid)


def main(argv):
    if len(argv) != 5:
        print("Usage: python fxgridder.py YYYY mm dd HH")
        return
    valid = datetime.datetime(int(argv[1]), int(argv[2]), int(argv[3]),
                              int(argv[4]), 0)
    valid = valid.replace(tzinfo=pytz.timezone("UTC"))
    run(valid)

if __name__ == '__main__':
    main(sys.argv)
