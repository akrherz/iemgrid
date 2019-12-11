"""What we currently archive

# LTBA98 KWBE   temperature 2m
# LRBA98 KWBE   relative humidity 2m
# LUBA98 KWBE   u wind 10m
# LVBA98 KWBE   v wind 10m
# LKBA98 KWBE   visibility 0m ???
# LEBB98 KWBE   precip

9:10 metre U wind component:m s**-1 (instant):lambert:heightAboveGround:
    level 10 m:fcst time 0 hrs:from 201512311800
10:10 metre V wind component:m s**-1 (instant):lambert:heightAboveGround:
    level 10 m:fcst time 0 hrs:from 201512311800

6:2 metre temperature:K (instant):lambert:heightAboveGround:level 2 m:
    fcst time 0 hrs:from 201512311800
7:2 metre dewpoint temperature:K (instant):lambert:heightAboveGround:
    level 2 m:fcst time 0 hrs:from 201512311800

445:Specific humidity:kg kg**-1 (instant):lambert:heightAboveGround:
    level 2 m:fcst time 0 hrs:from 201512311800
8:Relative humidity:% (instant):lambert:heightAboveGround:level 2 m:
    fcst time 0 hrs:from 201512311800

349:Visibility:m (instant):lambert:surface:level 0:fcst time 0 hrs:
    from 201512311800
11:Total Precipitation:kg m**-2 (accum):lambert:surface:level 0:
    fcst time 0 hrs (accum):from 201512311800
"""
import pygrib
import glob
import os
import sys
import subprocess

WANT = [
    "10 metre U wind component",
    "10 metre V wind component",
    "2 metre temperature",
    "Relative humidity",
    "Visibility",
    "Total Precipitation",
]
WANTLVL = [10, 10, 2, 2, 0, 0]


def process(fn):
    """Process a grib file into a smaller, grib file..."""

    # nam_218_20151231_1800_000.grb2
    grbs = pygrib.open(fn)
    (_, _, yyyymmdd, hhmi, hhh) = fn.split(".")[0].split("_")
    if int(hhh) % 3 != 0:
        os.unlink(fn)
        return
    newfn = "%s%sF%s.grib2" % (yyyymmdd, hhmi, hhh)
    newdir = ("%s/%s/%s/grib2/ncep/NAM218/%s") % (
        yyyymmdd[:4],
        yyyymmdd[4:6],
        yyyymmdd[6:],
        hhmi[:2],
    )
    if not os.path.isdir(newdir):
        os.makedirs(newdir)
    # 201611101200F003.grib2
    print("%s -> %s %s" % (fn, newdir, newfn))
    o = open("%s/%s" % (newdir, newfn), "wb")
    for grb in grbs:
        if grb.name in WANT:
            if grb.level == WANTLVL[WANT.index(grb.name)]:
                o.write(grb.tostring())
    o.close()
    os.unlink(fn)


def dodir(mydir):
    os.chdir(mydir)
    for tarfn in glob.glob("*.tar"):
        subprocess.call("tar -xf %s" % (tarfn,), shell=True)
        for grib2fn in glob.glob("*.grb2"):
            process(grib2fn)


def main(argv):
    dodir(argv[1])


if __name__ == "__main__":
    main(sys.argv)
