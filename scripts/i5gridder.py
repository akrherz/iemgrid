"""The wx gridder!
  "wawa"     Gridded NWS Watch Warning Advisory codes
  "ptype"    Precip type (int flag) -> MRMS
  "tmpc"     2m Air Temperature
  "dwpc"     2m Dew Point
  "smps"     10m Wind Speed
  "drct"     10m Wind Direction (no u/v components)
  "vsby"     Visibility, understanding that I can't go down below 1/8 mile
  "roadtmpc" Pavement Temp, very crude regridding of RWIS data
  "srad"     Solar Radiation (2014 onward)
  "snwd"     Snow Depth would be once per day


"""
import sys
import datetime
import pytz
import socket
import numpy as np
from pyiem import reference

XAXIS = np.arange(reference.IA_WEST, reference.IA_EAST - 0.01, 0.01)
YAXIS = np.arange(reference.IA_SOUTH, reference.IA_NORTH - 0.01, 0.01)
PROGRAM_VERSION = 0.1
DOMAIN = {'wawa': {'units': '1'},
          'ptype': {'units': '1'},
          'tmpc': {'units': 'C'},
          'dwpc': {'units': 'C'},
          'smps': {'units': 'mps'},
          'drct': {'units': 'deg'},
          'vsby': {'units': 'km'},
          'roadtmpc': {'units': 'C'},
          'srad': {'units': 'Wm*{-2}'},
          'snwd': {'units': 'mm'}
          }


def write_grids(grids, valid):
    """Do the write to disk"""
    for label in grids:
        thisgrid = grids[label]
        fn = "/tmp/%s_%s.xml" % (label, valid.strftime("%Y%m%d%H%M"))
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
                out.write(('<cell gid="%s">%.2f</cell>'
                           ) % (i, thisgrid[row, col]))
                i += 1
            out.write("\n")
        out.close()


def init_grids():
    """Create the grids, please"""
    grids = {}
    for label in DOMAIN:
        grids[label] = np.zeros((324, 660), np.float32)

    return grids


def run(valid):
    """Run for this timestamp (UTC)"""
    grids = init_grids()
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
