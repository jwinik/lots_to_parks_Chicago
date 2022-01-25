#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 15 12:59:19 2021

@author: isabellehirschy, kashifahmed2, jwinik
"""
import pandas as pd
from shapely.geometry import Point, MultiPolygon
from shapely.ops import transform
import geopandas as gpd
import matplotlib.pyplot as plt
from pygeoif import geometry
import os
from shapely.geometry.multipoint import MultiPointAdapter
from shapely.geometry.multipolygon import MultiPolygon
import statsmodels.api as sm
import statsmodels.formula.api as smf
from sodapy import Socrata
from shapely.geometry import shape
from pandas.io.json import json_normalize
import pyproj
import seaborn as sns


PATH =  os.path.abspath(os.getcwd())
PATH = r"/Users/isabellehirschy/Documents/Harris/final-project-final-project-izzie-kashif-jason/"
# ------------------------------------------------------------------------------
# ------------------------------ FUNCTIONS -------------------------------------
# ------------------------------------------------------------------------------

def api_get(fname):
    '''
    Uses socrata and city of chicago website to get JSON and converts to Data
    '''
    client = Socrata("data.cityofchicago.org", None)
    results = client.get(fname, limit = 20005)
    df = pd.DataFrame.from_records(results)
    return df

def read_lots(api_key="aksk-kvfp"):
    '''
    Converts dataframe to geodataframe
    '''
    df = api_get(api_key)
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["x_coordinate"], df["y_coordinate"]))
    gdf = gdf.dropna(subset=["address", "location", ":@computed_region_rpca_8um6", "latitude", "longitude"])
    gdf = gdf.set_crs("ESRI: 102671")
    return gdf

def fix_geom(df, geom='the_geom'):
    df['geometry'] = df[str(geom)].apply(lambda row:geometry.as_shape(row))
    return df

def re_proj(row):
    '''
    Converts points in WGS84 to IL Projected Coordinates
    '''
    proj = pyproj.Proj('+proj=tmerc +lat_0=36.66666666666666 +lon_0=-88.33333333333333 +k=0.9999749999999999 +x_0=300000 +y_0=0 +ellps=GRS80 +datum=NAD83 +to_meter=0.3048006096012192 +no_defs')
    x, y = proj(row["longitude"], row["latitude"])
    return x, y

def gdf_proj(df):
    '''
    Creates a geodataframe using projected coordinates
    '''
    df["projected_coord"] = df.apply(re_proj, axis=1)
    x = []
    y = []
    for tuple in df["projected_coord"]:
        a, b = tuple
        x.append(a)
        y.append(b)
    df["x"] = x
    df["y"] = y
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["x"], df["y"]))
    return gdf

def csv_to_gdf(csv_name):
    df = pd.read_csv(os.path.join(PATH,csv_name))
    df['Coordinates'] = df['Map Site CSV'].str.split('GEOSEARCH:').str[1]
    df[['latitude', 'longitude']] = df.pop('Coordinates').str.split(' ', 1, expand=True)
    df = df[df.longitude != ""]
    df = df[df.latitude != ""]
    gdf = gdf_proj(df)
    return gdf

def read_bf(csv=r"CIMC Basic Search Result.csv"):
    gdf = csv_to_gdf(csv)
    gdf = gdf.set_crs("ESRI: 102671")
    return gdf

def check_tuple(gdf):
    #col_list = []
    for col in gdf.columns:
        print(col, 'is a tuple : ', all(isinstance(x,tuple) for x in gdf[col]))

def find_centroid(df):
    '''
    Finds the centroid of a multipolygon and returns a column
    '''
    centroids = []
    for multipolygon in df["geometry"]:
        center = multipolygon.centroid
        centroids.append(center)
    df["centroid"] = centroids
    return df

def proj_transform(df, to_wgs=True, geom_col="geometry", epsg="EPSG: 4326"):
    '''
    Converts existing Point objects to different projections
    '''
    reprojections = []
    if to_wgs == True:
        for point in df[geom_col]:
            inproj = pyproj.CRS('+proj=tmerc +lat_0=36.66666666666666 +lon_0=-88.33333333333333 +k=0.9999749999999999 +x_0=300000 +y_0=0 +ellps=GRS80 +datum=NAD83 +to_meter=0.3048006096012192 +no_defs')
            project = pyproj.Transformer.from_crs(inproj, epsg, always_xy=True).transform
            new_point = transform(project, point)
            reprojections.append(new_point)
    else:
        for point in df[geom_col]:
            outproj = pyproj.CRS('+proj=tmerc +lat_0=36.66666666666666 +lon_0=-88.33333333333333 +k=0.9999749999999999 +x_0=300000 +y_0=0 +ellps=GRS80 +datum=NAD83 +to_meter=0.3048006096012192 +no_defs')
            project = pyproj.Transformer.from_crs(epsg, outproj, always_xy=True).transform
            new_point = transform(project, point)
            reprojections.append(new_point)
    df["geometry_reproj"] = reprojections
    return df

def read_park_nbh(api_key, park=False):
    df = api_get(api_key)
    df = fix_geom(df)
    gdf = gpd.GeoDataFrame(df, geometry=df["geometry"])
    gdf = gdf.set_crs("EPSG:4326")
    if park == True:
        gdf = find_centroid(gdf)
        gdf = proj_transform(gdf, to_wgs=False, geom_col="centroid")
    return gdf

def read_bus(api_key="qs84-j7wh"):
    df = api_get(api_key)
    df = df.rename(columns={"point_x":"longitude", "point_y":"latitude"})
    gdf = gdf_proj(df)
    streets = "55th|Garfield|63rd|79th|Ashland|Chicago|Lake Shore|Western"
    gdf = gdf[gdf["street"].str.contains(streets,case=False)]
    return gdf

def read_el(api_key="8pix-ypme"):
    df = api_get(api_key)
    for idx, row in df.iterrows():
        df.loc[idx, 'latitude'] = df['location'][idx]['latitude']
        df.loc[idx, 'longitude'] = df['location'][idx]['longitude']
    gdf = gdf_proj(df)
    return gdf

def is_near(coordinate, df, distance, geom_column="geometry"):
    '''
    Takes coordinate and dataframe and counts if within buffer zone 
    '''
    counter = 0
    circle_buffer = coordinate.buffer(distance)
    for station in df[str(geom_column)]:
        if station.within(circle_buffer):
            counter += 1
    return counter

def near_counter(gdf, comp_gdf, near_col, distance=2500, geom_column="geometry"):
    '''
    Creates new column for how close lot is to other points
    '''
    near = []
    for point in gdf["geometry"]:
        counter = is_near(point, comp_gdf, distance, geom_column)
        near.append(counter)
    gdf[near_col] = near
    return gdf

def find_eligibility(df, elig_col, elig_list, new_col_name):
    '''
    Finds program eligibility for the lots
    '''
    eligible = []
    for lot in df[elig_col]:
        if lot in elig_list:
            eligible.append(1)
        else:
            eligible.append(0)
    df[new_col_name] = eligible
    return df
    
def find_candidates(row):
    '''
    Finds candidates using progam eligibility and parameters of interest 
    '''
    if row["ANLAP Eligible"] + row["Large Lots Eligible"] >= 1:
        score = row["Near El"] + (row["Near Bus"]/10) + row["Invest SW Eligible"] - row['Near Park'] - row['Near Brownfield']
    else:
        score = 0
    return score

def make_shp(df, file_name, to_drop=["geometry_reproj", "projected_coord"]):
    df = df[df["latitude"] != "0"]
    df = proj_transform(df)
    df["geometry"] = df["geometry_reproj"]
    df = df.drop(to_drop, axis=1)
    df.to_file(os.path.join(PATH,'shapefiles', file_name+'.shp'))
    
def make_shp_park_nbh(df, file_name, park=False):
    if park == True:
        if os.path.exists(os.path.join(PATH,'shapefiles','parks.shp')):
            print("parks shapefile exists")
        else:
            df = df.drop(["centroid", "geometry_reproj"], axis=1)
            df.to_file(os.path.join(PATH, 'shapefiles', file_name+'.shp'))
    else:
        df.to_file(os.path.join(PATH, 'shapefiles', file_name+'.shp'))

# function saves time in reprojections
def model_df(api_key1, csv, api_key2, crs):
    lots = api_get(api_key1)
    lots = gpd.GeoDataFrame(lots, geometry=gpd.points_from_xy(lots["longitude"], lots["latitude"]))
    lots = lots.dropna(subset=["address", "location", ":@computed_region_rpca_8um6", "latitude", "longitude"])
    lots = lots.set_crs(crs)
    bf = pd.read_csv(os.path.join(PATH,csv))
    bf['Coordinates'] = bf['Map Site CSV'].str.split('GEOSEARCH:').str[1]
    bf[['latitude', 'longitude']] = bf.pop('Coordinates').str.split(' ', 1, expand=True)
    bf = bf[bf.longitude != ""]
    bf = bf[bf.latitude != ""]
    bf = gpd.GeoDataFrame(bf, geometry=gpd.points_from_xy(bf["longitude"], bf["latitude"]))
    bf = bf.set_crs(crs)
    nbh = api_get(api_key2)
    nbh = fix_geom(nbh)
    nbh = gpd.GeoDataFrame(nbh, geometry=nbh["geometry"])
    nbh = nbh.set_crs(crs)
    bf_nbh = nbh.sjoin(bf, how='inner', predicate='intersects')
    bf_nbh = bf_nbh.groupby(['pri_neigh']).size().reset_index(name='bf_count')
    lots_nbh = nbh.sjoin(lots, how='inner', predicate='intersects')
    lots_nbh = lots_nbh.groupby(['pri_neigh']).size().reset_index(name='lots_count')
    df = lots_nbh.merge(bf_nbh, how ='left', on='pri_neigh')
    df = df.fillna(0)

    return df

def reg(df):
    results = smf.ols(formula = "lots_count ~ bf_count", data=df).fit()
    return results

def graph(df):
    p  = sns.regplot(df['bf_count'], df['lots_count'])
    p.set_ylabel('Number of Vacant Lots')
    p.set_xlabel('Number of Brownfields')
    p.set_title('Relationship between pollution and lots per neighborhood');
    fig = p.get_figure()
    return fig


# ------------------------------------------------------------------------------
# ----------------------------- Data Manipulation ------------------------------
# ------------------------------------------------------------------------------

# Read all 5 data frames - Lots, Park, Bus, "L" Station, Brownfields into GDF

gdf = read_lots()
gdf_park = read_park_nbh("ejsh-fztr", park=True)
gdf_nbh = read_park_nbh("y6yq-dbs2")
gdf_bus = read_bus()
gdf_el = read_el()
gdf_bf = read_bf()

# -----------
# Create "Near _____" variable
# -----------

gdf = near_counter(gdf, gdf_park, "Near Park", geom_column="geometry_reproj")
gdf = near_counter(gdf, gdf_bus, "Near Bus")
gdf = near_counter(gdf, gdf_el, "Near El")
gdf = near_counter(gdf, gdf_bf, "Near Brownfield")

# -----------
#  Eligibility Invest SW, Large Lots, and ANLAP
# -----------

invest_sw = ["AUBURN GRESHAM", "AUSTIN", "BRONZEVILLE", "ENGLEWOOD", "NEW CITY", "NORTH LAWNDALE", "GREATER ROSELAND", "SOUTH CHICAGO"]
anlap = ["RM-5", "RT-4", "RS-1", "RS-2", "RS-3"]
large_lots = ['RS-2', 'RS-3', 'RT-4', 'RM-5', 'RT-4A', 'RM-4.5', 'RM-6', 'RS-1','RM-5.5', 'RT-3.5', 'RM-6.5']

gdf = find_eligibility(gdf, "community_area_name", invest_sw, "Invest SW Eligible")
gdf = find_eligibility(gdf, "zoning_classification", anlap, "ANLAP Eligible")
gdf = find_eligibility(gdf, "zoning_classification", large_lots, "Large Lots Eligible")

# -----------
# Create Index
# -----------

gdf["score"] = gdf.apply(find_candidates, axis=1)

# export variable files to shapefile for jupyter notebook
    
make_shp(gdf, "lots", to_drop="geometry_reproj")
make_shp_park_nbh(gdf_park, "parks", park=True)
make_shp(gdf_bus, "bus_stops")
make_shp(gdf_el, "el_stops")
make_shp(gdf_bf, "pollution")
make_shp_park_nbh(gdf_nbh, "neighborhoods")
# ------------------------------------------------------------------------------
# ----------------------------- Model ------------------------------------------
# ------------------------------------------------------------------------------

# to be generalized

df = model_df("aksk-kvfp", r"CIMC Basic Search Result.csv", "y6yq-dbs2", "EPSG:3435")

results = reg(df)

print(results.summary())

fig = graph(df)

fig.savefig('bf_lots.png')


# ------------------------------------------------------------------------------
# ----------------------------- Visualizations ---------------------------------
# ------------------------------------------------------------------------------

# See Jupyter Notebook
nbh = api_get("y6yq-dbs2")
nbh = fix_geom(nbh)
nbh = gpd.GeoDataFrame(nbh, geometry=nbh["geometry"])
nbh = nbh.set_crs("EPSG:3435")
nbh.to_file(os.path.join(PATH,'shapefiles', 'nbh.shp'))

"""
Citations

https://gis.stackexchange.com/questions/192362/check-if-point-is-within-radius-of-another-point-with-shapely
https://automating-gis-processes.github.io/CSC18/lessons/L4/point-in-polygon.html
https://docs.astraea.earth/hc/en-us/articles/360043923831-Read-a-KML-File-into-a-GeoPandas-DataFrame
https://geopandas.org/en/stable/gallery/create_geopandas_from_pandas.html
https://dev.socrata.com/foundry/data.cityofchicago.org/aksk-kvfp
https://www.py4u.net/discuss/149413
https://towardsdatascience.com/nearest-neighbour-analysis-with-geospatial-data-7bcd95f34c0e
https://stackoverflow.com/questions/64778883/how-to-identify-columns-which-contain-only-tuples-in-pandas
"""
