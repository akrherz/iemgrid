12 Nov 2015
-----------
- Discussion of the data format and other aux issues
- [ ] Additional variables
  - Gridded NWS Watch Warning Advisory codes
- xml file wrapped with <wx>
- time expressed as ISO
- Discussion of timing of forecasts
- use English units in xml

29 Oct 2015
-----------
- This was the initial meeting to get work kicked off
- NTRANS is interested in anything that impeeds traffic flow
- For realtime purposes, there is some latencies involved with their other
vendors of data.  They need time to collect up enough samples to make for
appropriate statistics.
- They are looking for an XML feed of data
- They use UTMz15, but are likely OK with Lat/Long WGS84
- Decision was to go with 1 Jan 1997 as start date
- 5 minute interval in time
- Timestamps would be presented as UTC
- Express Precipitation in Hourly Rates
- [ ] Variables to deliver
  - Precip type (int flag)
  - 2m Air Temperature
  - 2m Dew Point
  - 10m Wind Speed
  - 10m Wind Direction (no u/v components)
- [ ] Additional Variables that will have lots of caveats
  - Visibility, understanding that I can't go down below 1/8 mile
  - Pavement Temp, very crude regridding of RWIS data
  - Solar Radiation (2014 onward)
  - Snow Depth would be once per day
- MADIS was discussed, but no real conclusion reached about it
- [ ] deliver format example by 20 November
- [ ] stand-up IEM TMS services for these variables
- usage of NDFD grids to drive forecast grids of the above
