"""Create a baseline XML file that represents the grid definition for work"""
import numpy as np
import pyiem.reference as reference

out = open("weather_grid.xml", "w")
out.write(
    """<?xml version="1.0" encoding="UTF-8"?>
<grid>
<title>IEM Weather Analysis Grid</title>
<revision>2016-02-24T22:00:00Z</revision>
<projection>EPSG:4326</projection>
<cellreference>lowerleft</cellreference>
<cells>
"""
)
i = 0
for rownum, lat in enumerate(
    np.arange(reference.IA_SOUTH, reference.IA_NORTH - 0.01, 0.01)
):
    for colnum, lon in enumerate(
        np.arange(reference.IA_WEST, reference.IA_EAST - 0.01, 0.01)
    ):
        i += 1
        out.write(
            (
                '<cell row="%s" col="%s" gid="%s">'
                "<lon>%.2f</lon><lat>%.2f</lat></cell>\n"
            )
            % (rownum + 1, colnum + 1, i, lon, lat)
        )

out.write("""</cells></grid>""")
out.close()
print("Largest gid is %s" % (i,))
