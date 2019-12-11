"""Mess around with wx grid definitions"""
import pyiem.reference as reference
import numpy as np

out = open("weather_data.xml", "w")
out.write(
    """<?xml version="1.0" encoding="UTF-8"?>
<wx>
<title>IEM Weather Grid</title>
<metadata>
  <time>2015-11-24T16:00:00Z</time>
  <revision>0.1</revision>
  <runtime units="seconds">30</runtime>
  <hostname>laptop.local</hostname>
</metadata>
<variable name="airtemp" units="F" type="analysis" valid="2015-11-24T16:00:00Z">
"""
)
i = 1
for rownum, lat in enumerate(
    np.arange(reference.IA_SOUTH, reference.IA_NORTH, 0.01)
):
    for colnum, lon in enumerate(
        np.arange(reference.IA_WEST, reference.IA_EAST, 0.01)
    ):
        out.write(('<cell gid="%s">32.2</cell>\n') % (i,))
        i += 1

out.write(
    """</variable>
<variable name="airtemp" units="F" type="forecast" valid="2015-11-25T16:00:00Z">
"""
)

i = 1
for rownum, lat in enumerate(
    np.arange(reference.IA_SOUTH, reference.IA_NORTH, 0.01)
):
    for colnum, lon in enumerate(
        np.arange(reference.IA_WEST, reference.IA_EAST, 0.01)
    ):
        out.write(('<cell gid="%s">32.2</cell>\n') % (i,))
        i += 1

out.write("""</variable>\n</wx>""")
