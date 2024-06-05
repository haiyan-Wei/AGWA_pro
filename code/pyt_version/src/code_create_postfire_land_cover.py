# -------------------------------------------------------------------------------
# Name:        code_create_postfire_land_cover.py
# Purpose:     Script for running the Burn Severity Tool
# -------------------------------------------------------------------------------

# Imports
import os
import arcpy
import AGWA_LandCoverMod
import importlib
importlib.reload(AGWA_LandCoverMod)
import pandas as pd

def execute(workspace, prjgdb, burn_severity_map, severity_field, land_cover_raster, change_table, output_location, 
            output_name):

    arcpy.env.workspace = output_location

    # get AGWA directory and look up table  
    meta_workspace_table = os.path.join(prjgdb, "metaWorkspace")
    if arcpy.Exists(meta_workspace_table):
        df_workspace = pd.DataFrame(arcpy.da.TableToNumPyArray(meta_workspace_table, "*"))
    else:
        raise Exception(f"The table 'metaWorkspace' does not exist in the workspace {prjgdb}.")
    agwa_directory = df_workspace["AGWADirectory"].values[0]
    change_table = os.path.join(agwa_directory, "lookup_tables.gdb", change_table)

    # Check the coordinate systems of the burn severity map and the land cover raster
    AGWA_LandCoverMod.tweet(f"Checking coordinate systems ...")
    AGWA_LandCoverMod.check_projection(burn_severity_map, land_cover_raster)

    # Burn Severity Tool requires the Spatial Analyst license
    AGWA_LandCoverMod.tweet(f"Checking out the Spatial Analyst License ...")
    AGWA_LandCoverMod.check_license("spatial", True)
    AGWA_LandCoverMod.tweet(f"... Spatial Analyst license checked out successfully!")

    # Execute the BurnSeverity function
    AGWA_LandCoverMod.tweet(f"Executing Burn Severity tool ...")
    AGWA_LandCoverMod.create_burn_severity_lc(burn_severity_map, severity_field, land_cover_raster,
                                              change_table, output_location, output_name)
    AGWA_LandCoverMod.tweet(f"... Burn Severity tool executed successfully!")

    created_lc = os.path.join(output_location, output_name + ".tif")
    arcpy.env.workspace = workspace
    arcpy.CopyRaster_management(created_lc, os.path.join(workspace, output_name))
    arcpy.Delete_management(output_location)
    
    # add the output to the map
    m = arcpy.mp.ArcGISProject("CURRENT").activeMap
    m.addDataFromPath(os.path.join(workspace, output_name))

