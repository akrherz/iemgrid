"""Mess around with wx grid definitions"""
import numpy as np
import pyiem.reference as reference

with open("weather_data.xml", "w", encoding="ascii") as fh:
    fh.write(
        """
<?xml version="1.0" encoding="UTF-8"?>
<wx>
<title>IEM Weather Grid</title>
<metadata>
<time>2015-11-24T16:00:00Z</time>
<revision>0.1</revision>
<runtime units="seconds">30</runtime>
<hostname>laptop.local</hostname>
</metadata>
<variable name="airtemp" units="F" type="analysis"
 valid="2015-11-24T16:00:00Z">
    """
    )
    i = 1
    for rownum, lat in enumerate(
        np.arange(reference.IA_SOUTH, reference.IA_NORTH, 0.01)
    ):
        for colnum, lon in enumerate(
            np.arange(reference.IA_WEST, reference.IA_EAST, 0.01)
        ):
            fh.write(f'<cell gid="{i}">32.2</cell>\n')
            i += 1

    fh.write(
        """
</variable>
<variable name="airtemp" units="F" type="forecast"
 valid="2015-11-25T16:00:00Z">
    """
    )

    i = 1
    for rownum, lat in enumerate(
        np.arange(reference.IA_SOUTH, reference.IA_NORTH, 0.01)
    ):
        for colnum, lon in enumerate(
            np.arange(reference.IA_WEST, reference.IA_EAST, 0.01)
        ):
            fh.write(f'<cell gid="{i}">32.2</cell>\n')
            i += 1

    fh.write("""</variable>\n</wx>""")
