# iemgrid

IEM Gridded Analysis code in support of sponsored work by NTRANS.

The analysis grid is a simple rectangular longitude + latitude grid at
resolution 0.01 degrees in both directions.  The outside corners are:

    -96.70 40.37 `pyiem.reference.IA_WEST` and `....IA_SOUTH`
    -90.10 43.61 `pyiem.reference.IA_EAST` and `....IA_NORTH`

So lets be clear here about how many grid cells this is.  The upper right
corner would have a lower-left vertex at `-90.09 43.60` so we yield
`660` pixels in the x-direction and `324` cells in the y-direction.

We are going to maintain a cell ID system that begins with `1` for the lower
left cell and increases horizontally then vertically ending with `213840`.

## Realtime Gridded Variables

### "wawa"

These are watches, warnings, and advisories issued by the National Weather Service.
These alerts **do not** cover all alert types issued by the NWS, but just those
that contain a special coding called VTEC.  Having said that, the VTEC enabled
products cover most everything that matters.

The alerts are presented by a string encoding of the VTEC phenomena and
significance values.  You can find a lookup table of these in the
[i5gridder.py code](/scripts/i5gridder.py).  Since multiple alerts can
be active at the same time, multiple codes can be found as active at one time.
These are seperated by commas when necessary. 

### "ptype"

This field is directly generated from the NOAA MRMS
project.  They use the following integer codes to present the state of
precipitation being estimated by RADAR and model algorithms.

Code | Representation
-----|---------------
-3 | no coverage
0 | no precipitation
1 | warm stratiform rain
2 | warm stratiform rain
3 | snow
4 | snow
5 | reserved for future use
6 | convective rain
7 | rain mixed with hail
8 | reserved for future use
9 | flag no longer used
10 | cold stratiform rain
91 | tropical/stratiform rain mix
96 | tropical/convective rain mix


### "tmpc"

Two meter above ground level air temperature.  This value would be over a
typical landscape for the location and not necessarily concrete, except in
very urban areas.

### "dwpc"

Two meter above ground level dew point temperature.  As with "tmpc", the same
landscape assumptions apply.

### "smps"

Ten meter above ground level wind speed.  This speed does not include gusts,
but is some average over a couple of minute period.

### "drct"

Wind direction, where the wind is blowing from, at ten meters above ground level.

### "vsby"

Horizontal visibility from automated sensors.

### "roadtmpc"

Pavement surface temperature derived from available RWIS reports.  These reports
include both bridge and approach deck temperatures.

### "srad"

Photoactive global solar radiation, sometimes called "shortwave down".

### "snwd"

Snowfall depth analyzed once per day at approximately 7 AM local time.  If
the reported snowfall depth was zero at 7 AM and it started snowing at noon,
this field would still be zero until it updated the next day at 7 AM.
  
### "pcpn"

Five minute precipitation accumulation ending at the time of analysis. This is
liquid equivelent.  So snow and sleet are melted to derive this value.

