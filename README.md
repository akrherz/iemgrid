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
