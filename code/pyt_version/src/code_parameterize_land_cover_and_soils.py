import os
import math
import arcpy
import tempfile
import arcpy.analysis
import numpy as np
import pandas as pd
from datetime import datetime

t0 = datetime.now()

def tweet(msg):
    """Produce a message for both arcpy and python"""
    m = "\n{}\n".format(msg)
    arcpy.AddMessage(m)
    print(m, arcpy.GetMessages())


def initialize_workspace(delineation_name, discretization_name, parameterization_name, prjgdb, land_cover_path,
                         land_cover_lut_path, soil_layer_path, soils_database_path, max_horizons, max_thickness, channel_type):
    """Initialize the workspace and write user's input to the metaParameterization table."""


    tweet("Checking if metaParameterization table exists")
    meta_parameterization_table = os.path.join(prjgdb, "metaParameterization")
    if not arcpy.Exists(meta_parameterization_table):
        raise Exception(f"The table 'metaParameterization' does not exist in the project GeoDataBase {prjgdb}."
                        f"Please run the Step 4 Parameterize Elements first.")
    

    tweet("Documenting user's input to metaParameterization table")
    fields = ["DelineationName", "DiscretizationName", "ParameterizationName", 
              "SlopeType", "FlowLengthMethod", "HydraulicGeometryRelationship", 
              "ChannelType", "LandCoverPath", "LandCoverLookUpTablePath",
              "SoilsPath", "SoilsDatabasePath", "MaxHorizons", "MaxThickness",
              "CreationDate", "AGWAVersionAtCreation", "AGWAGDBVersionAtCreation", "Status"]

    row_list = [delineation_name, discretization_name, parameterization_name, 
                "", "", "", channel_type, land_cover_path, land_cover_lut_path, 
                soil_layer_path, soils_database_path, max_horizons, max_thickness,
                datetime.now().isoformat(), "4.0", "4.0", "X"]
    
    with arcpy.da.UpdateCursor(meta_parameterization_table, fields) as cursor:
        for row in cursor:
            if (row[0] == delineation_name and row[1] == discretization_name and
                row[2] == parameterization_name):
                row[6:] = row_list[6:]
                cursor.updateRow(row)


def parameterize(prjgdb, workspace, delineation_name, discretization_name, parameterization_name, save_intermediate_outputs):

    """Parameterize land cover and soils for each hillslope and channel in the watershed. main function.
    functions called: extract_parameters, intersect_soils, weight_hillsope_parameters_by_area_fractions, 
    intersect_weight_land_cover_by_area, parameterize_channels"""

    # Step 1. Extract parameters from the metadata tables 
    (max_thickness, max_horizons, land_cover, land_cover_lut, soil_feature_class_path, soils_database_path, 
     AGWA_directory, channel_type) = extract_parameters(prjgdb, delineation_name, discretization_name, parameterization_name)  
    
    
    # Step 2. Get weighted soils and land cover. Merge with other hillslope parameters (17 or 33 parameters)
    df_hillslope_parameters = parameterize_hillslopes(workspace, delineation_name, discretization_name, parameterization_name, 
                                                      soil_feature_class_path, soils_database_path, AGWA_directory,
                                                      max_thickness, max_horizons, land_cover, land_cover_lut, 
                                                      save_intermediate_outputs)
    # Step 3. Get channel elements
    df_channel_parameters = parameterize_channels(workspace, delineation_name, discretization_name, parameterization_name,
                                                  channel_type, df_hillslope_parameters, AGWA_directory)  
      
    # Step 4. write the hillslope tables to the workspace gdb
    for df, table_name in zip([df_hillslope_parameters, df_channel_parameters], ["parameters_hillslopes", "parameters_channels"]):
        tweet(f"Writing {table_name} to the workspace geodatabase")     
        with tempfile.TemporaryDirectory() as tempdir:
            temp_csvfile = os.path.join(tempdir, F'tempfile_{table_name}.csv')
            df.to_csv(temp_csvfile, index=False)            
            if arcpy.Exists(os.path.join(workspace, table_name)):
                arcpy.Delete_management(os.path.join(workspace, table_name))            
            arcpy.TableToTable_conversion(temp_csvfile, workspace, table_name)


def parameterize_hillslopes(workspace, delineation_name, discretization_name, parameterization_name, soil_feature_class_path,
                    soils_database_path, agwa_directory, max_thickness, max_horizons, land_cover, land_cover_lut, 
                    save_intermediate_outputs):
    
    """Parameterize hillslopes. Results: 33 parameters.
    Called in parameterize function."""

    # Step 1. intersect soils and land cover with hillslopes
    intersect_soils(workspace, delineation_name, discretization_name, parameterization_name, soil_feature_class_path,
                    soils_database_path, agwa_directory, max_thickness, max_horizons, save_intermediate_outputs)
    
    df_soil = weight_hillsope_parameters_by_area_fractions(workspace, delineation_name, discretization_name, parameterization_name, 
                save_intermediate_outputs)
    
    # Step 2. intersect land cover with hillslopes
    df_cover = intersect_weight_land_cover_by_area(workspace, discretization_name, land_cover, land_cover_lut, agwa_directory)
    df_soiL_cover = pd.merge(df_soil, df_cover, left_on="HillslopeID", right_on="HillslopeID", how="left")
    
    # Step 3. read hillslope table and merge with soil and land cover parameters, while keep previous sets intact
    df_hillslope = pd.DataFrame(arcpy.da.TableToNumPyArray(os.path.join(workspace, "parameters_hillslopes"), "*", null_value=-9999))
    df_hillslope = df_hillslope.drop(columns=["OBJECTID"])
    df_hillslope_current_set = df_hillslope[(df_hillslope["DelineationName"] == delineation_name) &
                                            (df_hillslope["DiscretizationName"] == discretization_name) &
                                            (df_hillslope["ParameterizationName"] == parameterization_name)]
    df_hillslope_previous_sets = df_hillslope[~df_hillslope.index.isin(df_hillslope_current_set.index)]

    df_hillslope_current_set.set_index("HillslopeID", inplace=True)
    df_soiL_cover.set_index("HillslopeID", inplace=True)
    for column in df_soiL_cover.columns:
        df_hillslope_current_set.loc[:,column] = df_soiL_cover.loc[:, column]
    df_hillslope_current_set.reset_index(inplace=True)
    
    # Step 4. merge the current set with previous sets
    df_hillslope_parameters = pd.concat([df_hillslope_previous_sets, df_hillslope_current_set], axis=0, ignore_index=True)

    return df_hillslope_parameters


def parameterize_channels(workspace, delineation_name, discretization_name, parameterization_name, channel_type, df_hillslope_parameters, agwa_directory):
    """Parameterize channel elements. Note: it is important to make sure parameters match in this function.
    Called in parameterize function."""    

    def get_channel_parameters_based_on_adj_hillslopes(workspace, delineation_name, discretization_name, parameterization_name,
                                                       df_hillslope_parameters):
        """Get channel parameters based on adjacent hillslopes. Called in parameterize_channels function.
        returned 17 parameters"""

        parameters = ["Ksat", "Manning", "Pave", "Imperviousness", "SMax", "CV", "G", "Porosity", "Rock",
                    "Sand", "Silt", "Clay", "Splash", "Cohesion", "Distribution", "BPressure"]
        
        df_hillslope_parameters = df_hillslope_parameters[(df_hillslope_parameters["DelineationName"] == delineation_name) & 
                                                (df_hillslope_parameters["DiscretizationName"] == discretization_name) & 
                                                (df_hillslope_parameters["ParameterizationName"] == parameterization_name)]                                             

        df_channels = pd.DataFrame(arcpy.da.TableToNumPyArray(os.path.join(workspace, f"{discretization_name}_channels"), 
                                                            ["ChannelID"]))

        for channel_id in df_channels.ChannelID:
            hillslope_ids = [channel_id-1, channel_id-2, channel_id-3]
            hillslope_ids = [hid for hid in hillslope_ids if hid in df_hillslope_parameters.HillslopeID.values]
            # print(channel_id, hillslope_ids) ## remove this when testing is done

            df_hillslopes_filtered = df_hillslope_parameters[df_hillslope_parameters.HillslopeID.isin(hillslope_ids)]
            total_area = df_hillslopes_filtered.Area.sum()
            for parameter in parameters:
                weighted_value = (df_hillslopes_filtered[parameter] * df_hillslopes_filtered.Area).sum() / total_area
                df_channels.loc[df_channels.ChannelID == channel_id, parameter] = weighted_value

        # Weight the texture factions, so that they sum to 1. When the sum of Sand, Silt, and Clay is 0, set them to 0.
        df_channels[["Sand", "Clay", "Silt"]] = df_channels[["Sand", "Clay", "Silt"]].div(
            df_channels[["Sand", "Clay", "Silt"]].sum(axis=1), axis=0).fillna(0)
        
        return df_channels


    # Step 1. get channel parameters based on weighted parameters from adjacent hillslopes (17 parameters in total)
    df_channel_parameters = get_channel_parameters_based_on_adj_hillslopes(workspace, delineation_name, discretization_name, 
                                                                           parameterization_name, df_hillslope_parameters)

    # Add one parameter (Woolhiser) (18 parameters in total),  assuming woolhiser channel type is always "Yes" for now.
    df_channel_parameters = df_channel_parameters.assign(Woolhiser="Yes")

    # Modify 3 parameters (ksat, manning, and pave) based on the user selected input channel type. 
    df_channel_type = pd.DataFrame(arcpy.da.TableToNumPyArray(
        os.path.join(agwa_directory, "lookup_tables.gdb", "channel_types"), "*", null_value=-9999))
    channel_type_row = df_channel_type[df_channel_type.Channel_Type == channel_type][["Ksat", "Manning", "Pave"]]
    if not channel_type_row.empty:
        ksat, manning, pave = channel_type_row.values[0]
        if ksat != -9999 and manning != -9999 and pave != -9999:
            df_channel_parameters = df_channel_parameters.assign(Ksat=ksat, Manning=manning, Pave=pave)
    else:
        tweet(f"Channel type {channel_type} not found in the Lookup table.")
        
    # Step 2. get current set of channel parameters separated from the previous sets (38 parameters in total)
    # df_channel and df_channel_previous_sets have 21 or 38 parameters, excluding OBJECTID. 21+18-1(ChannelID)=38 parameters
    df_channel = pd.DataFrame(arcpy.da.TableToNumPyArray(os.path.join(workspace, "parameters_channels"), "*"))
    df_channel = df_channel.drop(columns=["OBJECTID"])
    df_channel_current_set = df_channel[(df_channel["DelineationName"] == delineation_name) &
                                                        (df_channel["DiscretizationName"] == discretization_name) &
                                                        (df_channel["ParameterizationName"] == parameterization_name)]
    df_channel_previous_sets = df_channel[~df_channel.index.isin(df_channel_current_set.index)]

    # update df_channel_previous_sets with the new channel parameters
    df_channel_current_set.set_index("ChannelID", inplace=True)
    df_channel_parameters.set_index("ChannelID", inplace=True)
    for column in df_channel_parameters.columns:
        df_channel_current_set.loc[:,column] = df_channel_parameters.loc[:, column]
    df_channel_current_set.reset_index(inplace=True)

    # Step 4. merge the current set with previous sets
    df_channel_parameters = pd.concat([df_channel_previous_sets, df_channel_current_set], axis=0, ignore_index=True)


    return df_channel_parameters


def intersect_weight_land_cover_by_area(workspace, discretization_name, land_cover, land_cover_lut, agwa_directory):

    """Intersect land cover with hillslopes and calculate weighted parameters for each hillslope.
    called in parameterize function."""

    # convert land cover raster to polygon, then intersect with hillslopes
    hillslope_feature_class = os.path.join(workspace, f"{discretization_name}_hillslopes")
    land_cover_feature_class = os.path.join(workspace, f"{discretization_name}_land_cover")
    intersect_feature_class = os.path.join(workspace, f"{discretization_name}_land_cover_PairwiseIntersect")

    if arcpy.Exists(land_cover_feature_class):
        arcpy.Delete_management(land_cover_feature_class) ## delete this when testing is done
    if arcpy.Exists(intersect_feature_class):
        arcpy.Delete_management(intersect_feature_class) ## delete this when testing is done
    land_cover = arcpy.sa.Int(land_cover)
    arcpy.RasterToPolygon_conversion(land_cover, land_cover_feature_class, "NO_SIMPLIFY", "VALUE")
    arcpy.analysis.PairwiseIntersect(f"'{land_cover_feature_class}'; '{hillslope_feature_class}'", intersect_feature_class, "ALL", None, "INPUT")

    
    df_cover_lut = pd.DataFrame(arcpy.da.TableToNumPyArray(
        os.path.join(agwa_directory, "lookup_tables.gdb", land_cover_lut), "*"))

    cover_lut_fields = ["CLASS", "NAME", "COVER", "INT", "N", "IMPERV"]
    df_cover_lut = df_cover_lut[cover_lut_fields]
    df_cover_lut = df_cover_lut.rename(columns={"NAME": "LandCoverClass", "COVER": "Canopy",
                                                "INT": "Interception", "N": "Manning", "IMPERV": "Imperviousness"}) 
    df_hillslope_cover = pd.DataFrame(arcpy.da.TableToNumPyArray(intersect_feature_class, ["HillslopeID", "gridcode", "Shape_Area"]))
    df_merge = pd.merge(df_hillslope_cover, df_cover_lut, left_on="gridcode", right_on="CLASS", how="left")  

    parameters = ["Canopy", "Interception", "Manning", "Imperviousness"]
    def weight_parameters(group, weight_column):
        weighted_par = pd.Series()
        for param in parameters:
            weighted_par[param] =  (group[param] * group[weight_column]).sum() / group[weight_column].sum()
        return pd.DataFrame([weighted_par])
        
    df_weighted = pd.DataFrame()
    for hillslope_id in df_merge.HillslopeID.unique():
        df_hillslope = df_merge[df_merge.HillslopeID == hillslope_id]
        df_weighted_values = weight_parameters(df_hillslope, "Shape_Area")
        df_weighted_values.insert(0, "HillslopeID", hillslope_id)
        df_weighted = pd.concat([df_weighted, df_weighted_values], axis=0, ignore_index=True)

    return df_weighted


def intersect_soils(workspace, delineation_name, discretization_name, parameterization_name, soil_feature_class_path, 
                    gssurgo_gdb, agwa_directory, max_thickness, max_horizons, save_intermediate_outputs):

    """Intersect soils with gSSURGO tables and calculate parameters for each soil component, horizon, and texture.
       Outputs include tables that are saved to the workspace geodatabase.
       called in parameterize function."""
            
    # intersect soil
    hillslope_feature_class = os.path.join(workspace, f"{discretization_name}_hillslopes")
    soil_feature_class_name = os.path.split(soil_feature_class_path)[1]
    intersect_feature_class = os.path.join(workspace, f"{discretization_name}_{soil_feature_class_name}_intersection")
    if arcpy.Exists(intersect_feature_class):
        arcpy.Delete_management(intersect_feature_class)  
    arcpy.analysis.PairwiseIntersect(f"'{soil_feature_class_path}'; '{hillslope_feature_class}'", 
                                     intersect_feature_class, "ALL", None, "INPUT")
    
    
    # reading tables from AGWA directory and gSSURGO database
    component_table = os.path.join(gssurgo_gdb, "component")
    horizon_table = os.path.join(gssurgo_gdb, "chorizon")
    texture_table = os.path.join(gssurgo_gdb, "chtexture")
    texture_group_table = os.path.join(gssurgo_gdb, "chtexturegrp")
    kin_lut_table = os.path.join(agwa_directory, "lookup_tables.gdb", "kin_lut")
    
    # define fields needed and read tables into dataframes
    component_fields = ["cokey", "comppct_r", "mukey"]
    horizon_fields = ["cokey", "chkey", "hzdept_r", "hzdepb_r", "ksat_r", "sandtotal_r", "silttotal_r", "claytotal_r",
                      "dbthirdbar_r", "partdensity", "sieveno10_r", "kwfact"]
    texture_group_fields = ["chkey", "chtgkey", "texture"]
    texture_fields = ["chtgkey", "texcl", "lieutex"]
    kin_lut_fields = ["TextureName", "KS", "G", "POR", "SMAX", "CV", "SAND", "SILT", "CLAY", "DIST", "KFF", "BPressure"]
    df_mapunit = pd.DataFrame(arcpy.da.TableToNumPyArray(intersect_feature_class, ["mukey"]))
    df_component = pd.DataFrame(arcpy.da.TableToNumPyArray(component_table, component_fields, skip_nulls=False))
    df_horizon = pd.DataFrame(arcpy.da.TableToNumPyArray(horizon_table, horizon_fields))
    df_texture_group = pd.DataFrame(arcpy.da.TableToNumPyArray(texture_group_table, texture_group_fields))
    df_texture = pd.DataFrame(arcpy.da.TableToNumPyArray(texture_table, texture_fields))
    df_kin_lut = pd.DataFrame(arcpy.da.TableToNumPyArray(kin_lut_table, kin_lut_fields))

    # start processing each mukey found in the intersection feature class
    df_horizon_parameters_with_soil_textures = pd.DataFrame()
    df_horizon_parameters = pd.DataFrame()
    
    # Loop 1: process each mukey
    df_component.mukey = df_component.mukey.astype(str)
    df_mapunit.mukey = df_mapunit.mukey.astype(str)
    unique_mukeys = df_mapunit["mukey"].unique()
    for mukey in unique_mukeys:
        
        df_component_filtered = df_component[df_component["mukey"] == mukey]
        
        # Loop 2: process each component
        for _, row in df_component_filtered.iterrows():
            component_id = row.cokey
            ComponentPercentage = row.comppct_r           

            # Loop 3: process each horizon
            df_horizon_filtered = df_horizon[(df_horizon["cokey"] == component_id) & (df_horizon["hzdept_r"] < max_thickness)].reset_index(drop=True)
            if df_horizon_filtered.empty:
                continue
            horizon_count = 0            
            for _, row in df_horizon_filtered.iterrows():    
                horizon_count += 1
                if not (max_horizons == 0 or horizon_count <= max_horizons):
                    break
                horizon_id = row.chkey
                horizon_parameters = query_soil_horizon_parameters(row, horizon_count, max_horizons)
                horizon_parameters["MapUnitKey"] = mukey
                horizon_parameters["ComponentId"] = component_id
                horizon_parameters["ComponentPercentage"] = ComponentPercentage

                # Loop 4: process texture group  
                # there is a potential issue here: from the gSSURGO tables, 1 horizon can have multiple texture groups
                df_texture_group_filtered = df_texture_group[df_texture_group["chkey"] == horizon_id]
                for _, row in df_texture_group_filtered.iterrows():
                    texture_group_id, texture_in_group_table = row.chtgkey, row.texture

                    # Loop 5: process texture (Loop 5 is not used in VB file?)
                    for _, row in df_texture[df_texture["chtgkey"] == texture_group_id].iterrows():
                        texture = row.texcl if row.texcl != "None" else row.lieutex
                        # print(mukey, component_id, horizon_id, texture_group_id,texture_in_group_table, texture) ### remove this when testing is done              
                        new_row = {"MapUnitKey": mukey, "ComponentId": component_id, "HorizonId": horizon_id,
                                   "TextureGroupId": texture_group_id, "Texture": texture} 
                        df_horizon_parameters_with_soil_textures = pd.concat([df_horizon_parameters_with_soil_textures, pd.DataFrame([new_row])], axis=0, ignore_index=True)
                
                # Query the kin_lut table based on soil texture with the last "texture".
                texture_in_kinlut_flag, horizon_parameters = query_kin_lut_update_horizon_parameters(df_kin_lut, texture, horizon_parameters)
                if texture_in_kinlut_flag: 
                    horizon_parameters["TextureGroupId"] = texture_group_id
                    horizon_parameters["Texture"] = texture_in_group_table
                    horizon_parameters["Texture_texcl"] = texture
                    # The following code is from the original VB code, which assigns Pave = 1 when the texture is one of ["WB", "UWB", "ICE", "CEM", "IND", "GYP"].
                    # "BR" and "CEM_BR", both of which represent bedrock in the gSSURGO_CA database, are added to the list.
                    # "VAR", which means "variable" in the gSSURGO_CA database, is also added, but it needs to be confirmed if Pave=1 is correct for this type.
                    # The list could potentially be updated or expanded based on gSSURGO database in other states.
                    if texture_in_group_table in ["WB", "UWB", "ICE", "CEM", "IND", "GYP", "BR", "CEM_BR", "VAR"]:
                        horizon_parameters["Pave"] = 1
                        # When Pave=1, Sand, Clay and Silt are set to 0.33, 0.33, and 0.34, respectively. 
                        # The values do not matter, but they need to sum to 1, so K2 can be executed.
                        # Also, they will be excluded from the calculation of the weighted parameters.
                        horizon_parameters["Sand"] = 0.33
                        horizon_parameters["Clay"] = 0.33
                        horizon_parameters["Silt"] = 0.34

                    else:
                        horizon_parameters["Pave"] = 0

                    # Update horizon_parameters with the texture group and texture
                    df_horizon_parameters = pd.concat([df_horizon_parameters, pd.DataFrame([horizon_parameters])], axis=0, ignore_index=True)
                else:
                    # Note: If the 'texture_in_kinlut_flag' is False, the variables SMax, CV, Distribution, and BPressure will not hold any values.
                    # As a result, the execution of K2 will not be possible under this condition.
                    tweet(f"Texture {texture} is not found in the AGWA lookup table.") ### Should this be a warning or an error?
                    continue

    df_weighted_by_horizon, df_weighted_by_component = calculate_weighted_hillslope_soil_parameters(df_horizon_parameters)

    # Add the remaining columns to the all tables. Save them to the workspace gdb, combined with previous sets
    if save_intermediate_outputs:
        df_to_save = [df_horizon_parameters_with_soil_textures, df_horizon_parameters, df_weighted_by_horizon, df_weighted_by_component]
        table_names = ["parameters_soil_horizons_with_textures", "parameters_soil_horizons", "parameters_soil_weighted_by_horizon", "parameters_soil_weighted_by_component"]
    else:
        df_to_save = [df_weighted_by_horizon, df_weighted_by_component]
        table_names = ["parameters_soil_weighted_by_horizon", "parameters_soil_weighted_by_component"]

    for df, table_name in zip(df_to_save, table_names):
        arcgis_table = os.path.join(workspace, table_name)
        df.insert(0, "DelineationName", delineation_name)
        df.insert(1, "ParameterizationName", parameterization_name)
        df.insert(2, "DiscretizationName", discretization_name)
        df = df.assign(CreationDate=datetime.now(), AGWAVersionAtCreation="4.0", AGWAGDBVersionAtCreation="4.0", Status="X")

        if arcpy.Exists(arcgis_table):
            df_previous_sets = pd.DataFrame(arcpy.da.TableToNumPyArray(arcgis_table, "*"))
            df_previous_sets = df_previous_sets.drop(columns=["OBJECTID"])
            df_combined = pd.concat([df_previous_sets, df], axis=0, ignore_index=True)
        else:
            df_combined = df
        
        with tempfile.TemporaryDirectory() as tempdir:
            temp_csvfile = os.path.join(tempdir, F'tempfile_{table_name}.csv')
            df_combined.to_csv(temp_csvfile, index=False)            
            if arcpy.Exists(arcgis_table):
                arcpy.Delete_management(arcgis_table)
            arcpy.TableToTable_conversion(temp_csvfile, workspace, table_name)


def query_soil_horizon_parameters(row, horizon_count, max_horizons):
    """Query soil horizon parameters. Called in intersect_soils function."""
    
    if not (max_horizons == 0 or horizon_count <= max_horizons):
        return pd.Series()

    try: 
        # calculate horizon thickness and total thickness
        horizon_id = row.chkey
        # Horizon thickness=Bottom depth-Top depth (from gSSURGO chorizon table, bottom depth is always greater than top depth)
        horizon_thickness = row.hzdepb_r - row.hzdept_r 
        # SSURGO table has ksat in micrometers per second, which needs to be converted to mm/hr
        # 1 mm / 1000 mm * 3600 seconds / 1 hour
        horizon_ksat = row.ksat_r * 1 / 1000 * 3600 / 1
        # Calculate G based on ksat using relationship derived by Goodrich, 1990 dissertation
        # G = 4.83 * (1 / ksat) * 0.326
        # Note his calculation are in English units, so conversions from Ks in mm/hr to in/hr
        # is used in the equation to derive G in inches, which is then converted back to
        # Alternate calculate derived by Haiyan Wei 2016 is G = 362.41 * KS ^ -0.378
        horizon_g = 25.4 * (4.83 * (1 / (horizon_ksat / 25.4)) ** 0.326)

        horizon_sand = row.sandtotal_r / 100
        horizon_silt = row.silttotal_r / 100
        horizon_clay = row.claytotal_r / 100
        kwfact = row.kwfact
        if kwfact == 'None':
            kwfact = 0.2 # from VB code
        #TODO from Shea: update the reference for the following equations
        horizon_splash = 422 * float(kwfact) * 0.8
        if horizon_clay <= 0.22:
            horizon_cohesion = 5.6 * float(kwfact) / (188 - (468 * horizon_clay)
                                        + (907 * (horizon_clay ** 2))) * 0.5
        else:
            horizon_cohesion = 5.6 * float(kwfact) / 130 * 0.5
        bulk_density = row.dbthirdbar_r # dbthirdbar_r is moist bulk density
        specific_gravity = row.partdensity
        # sieve_no_10 is soil fraction passing a number 10 sieve (2.00mm square opening) as a weight
        # percentage of the less than 3 inch (76.4mm) fraction.
        # effectively percent soil
        sieve_no_10 = row.sieveno10_r
        horizon_rock = 1 - (sieve_no_10 / 100)
        # reference: https://water.usgs.gov/GIS/metadata/usgswrd/XML/ds866_ssurgo_variables.xml
        # porosity = 1 - ((bulk density) / (particle density))
        # bulk density = dbthirdbar_r from SSURGO chorizon table
        # particle density = partdensity from SSURGO chorizon table
        if not(math.isnan(bulk_density) or math.isnan(specific_gravity)):
            horizon_porosity = 1 - (bulk_density / specific_gravity)
        else:
            horizon_porosity = np.nan            
        # rock_by_weight = ((1 - horizon_porosity) * (1 - horizon_rock)) /
        # (1 - (horizon_porosity * (1 - horizon_rock)))

        new_row = {
            "HorizonId": horizon_id,
            "HorizonNumber": horizon_count,
            "HorizonTopDepth": row.hzdept_r,
            "HorizonBottomDepth": row.hzdepb_r,
            "HorizonThickness": horizon_thickness,
            "Ksat": horizon_ksat,
            "G": horizon_g,
            "Porosity": horizon_porosity,
            "Rock": horizon_rock,
            "Sand": horizon_sand,
            "Silt": horizon_silt,
            "Clay": horizon_clay,
            "kwfact": kwfact,
            "Splash": horizon_splash,
            "Cohesion": horizon_cohesion} # 15 parameters in total
        
        horizon_parameters = pd.DataFrame([new_row]).squeeze()
    
    except Exception as e:
        horizon_parameters = pd.Series()

    return horizon_parameters


def calculate_weighted_hillslope_soil_parameters(df):

    """Calculate weighted parameters for each horizon and component. Return two dataframes: one for horizon and one for component.
    14 parameters get weighted in this function.
    called in intersect_soils function. """

    # Note: in the original code, there is check on total horizon thickness:
    # if total_thickness == 0:
    #     total_component_pct -= component_pct
    #     cokey_with_missing_horizons.append(component_id)
    # In the gSSURGO_CA database, hzdept_r seems to be always less than hzdepb_r, therefore thickness is always positive.
    # Similarly, comppct_r is always positive, so total_component_pct will always be positive.
    # However, a check is added to ensure that the total thickness is not positive.
    
    number_of_horizons_with_nonpositive_thickness = sum(df.HorizonThickness<0)
    if number_of_horizons_with_nonpositive_thickness > 0:
        tweet((f"Warning: {number_of_horizons_with_nonpositive_thickness} horizons have non-positive thickness."
               "These horizons will be ignored in the calculation of weighted parameters."))
    df = df[df.HorizonThickness > 0]
    
    number_of_components_with_nonpositive_pct = sum(df.ComponentPercentage<0)
    if number_of_components_with_nonpositive_pct > 0:
        tweet((f"Warning: {number_of_components_with_nonpositive_pct} components have non-positive percentage."
               "These components will be ignored in the calculation of weighted parameters."))
    df = df[df.ComponentPercentage > 0]

    parameters = ["Ksat", "G", "Porosity", "Rock", "Sand", "Silt", "Clay", "Splash", "Cohesion", "Pave", "SMax", "CV", "Distribution", "BPressure"]

    df_weighted_horizon = pd.DataFrame()
    df_weighted_component = pd.DataFrame()

    def weight_parameters(group, weight_column):
        weighted_par = pd.Series()
        for param in parameters:
            weighted_par[param] = (group[param] * group[weight_column]).sum() / group[weight_column].sum()
        # weight the texture factions, so that they sum to 1
        total_particle = weighted_par['Sand'] + weighted_par['Silt'] + weighted_par['Clay']
        if total_particle != 0:
            weighted_par['Sand'] /= total_particle
            weighted_par['Silt'] /= total_particle
            weighted_par['Clay'] /= total_particle            
        return pd.DataFrame([weighted_par])
        
    for mukey in df.MapUnitKey.unique():
        df_soil = df[df.MapUnitKey == mukey]
        for component_id in df.ComponentId.unique():
            df_component = df_soil[df_soil.ComponentId == component_id]
            for horizon_id in df_component.HorizonId.unique():
                df_horizon = df_component[df_component.HorizonId == horizon_id]
                df_weighted_values = weight_parameters(df_horizon, "HorizonThickness")
                df_weighted_values.insert(0, "MapUnitKey", mukey)
                df_weighted_values.insert(1, "ComponentId", component_id)
                df_weighted_values.insert(2, "HorizonId", horizon_id)
                df_weighted_values.insert(3, "TotalHorizonThickness", df_horizon["HorizonThickness"].sum())                
                df_weighted_values.insert(4, "ComponentPercentage", df_horizon["ComponentPercentage"].values[0])
                df_weighted_horizon = pd.concat([df_weighted_horizon, df_weighted_values], axis=0, ignore_index=True)

    
    for mukey in df_weighted_horizon.MapUnitKey.unique():
        df_component = df_weighted_horizon[df_weighted_horizon.MapUnitKey == mukey]
        df_weighted_values = weight_parameters(df_component, "ComponentPercentage")
        df_weighted_values.insert(0, "MapUnitKey", mukey)
        df_weighted_values.insert(1, "TotalComponentPercentage", df_component["ComponentPercentage"].sum())   
        df_weighted_component = pd.concat([df_weighted_component, df_weighted_values], axis=0, ignore_index=True)
    
    return df_weighted_horizon, df_weighted_component


def query_kin_lut_update_horizon_parameters(df_kin_lut, texture, horizon_parameters):  
    """This function queries 'kin' parameters and updates 'horizon' values. It is called within the 'intersect_soils' function.
        Additionally, it computes 'cohesion' based on the 'clay' values from the 'kin_lut' table.
        Note: the 'kin_lut' table is prioritized over the SSURGO 'chorizon' table."""

    kin_par = df_kin_lut[df_kin_lut.TextureName == texture].squeeze()
    if kin_par.empty: 
        # this means the texture type from SSURGO is not found in the kin_lut table
        # in this case, there won't be values for SMax, CV, Distribution, and BPressure
        horizon_parameters["comment"] = "Texture not found in kin_lut table"
        return False, horizon_parameters


    # 13 parameters from kin_lut table
    kin_ksat = kin_par.KS
    kin_g = kin_par.G
    kin_porosity = kin_par.POR
    kin_smax = kin_par.SMAX
    kin_cv = kin_par.CV 
    kin_sand = kin_par.SAND/100
    kin_silt = kin_par.SILT/100
    kin_clay = kin_par.CLAY/100
    kin_distribution = kin_par.DIST
    kin_kff = kin_par.KFF  # used to calculate cohesion
    kin_bpressure = kin_par.BPressure  # need to confirm with Shea, the purpose of this parameter

    # TODO from Shea: document the splash and cohesion equations by adding references    
    # calculate cohesion based on kff (kwfact). modify if kf is 0 or kin_kff is negative
    kf = float(horizon_parameters["kwfact"])
    if kf == 0:
        if kin_kff <= 0:
            kf = 0.2
        else:
            kf = kin_kff
    splash = 422 * float(kf) * 0.8

    # calculate cohension
    # option 1: calculate cohesion based on clay content from SSURGO chorizon table
    if False: # use option 2
        if math.isnan(horizon_parameters["Clay"]):
            clay = kin_clay
        else:
            clay = horizon_parameters["Clay"]
    # option 2: calculate cohesion based on clay content from kin_lut
    clay = kin_clay

    if clay <= 0.22:
        cohesion = 5.6 * kf / (188 - (468 * clay) + (907 * (clay ** 2))) * 0.5
    else:
        cohesion = 5.6 * kf / 130 * 0.5

    # The following 8 parameters are computable from SSURGO
    # Use values from kin_lut unless parameter from kin_lut is null
    kin_values_to_use = {"Ksat": kin_ksat, "G": kin_g, "Sand": kin_sand,
                         "Silt": kin_silt, "Clay": kin_clay, "Splash": splash,
                         "Cohesion": cohesion, "Porosity": kin_porosity}
    for key, value in kin_values_to_use.items():
        if value is not None and not math.isnan(value):
            horizon_parameters[key] = value

    # the following 4 parameters are not computable from SSURGO, so they must come from kin_lut
    # these are required parameters for KINEROS2
    kin_values_to_add ={"SMax": kin_smax, "CV": kin_cv, 
                        "Distribution": kin_distribution, "BPressure": kin_bpressure}        
    for key, value in kin_values_to_add.items():
        horizon_parameters[key] = value
    
    return True, horizon_parameters


def weight_hillsope_parameters_by_area_fractions(workspace, delineation_name, discretization_name, parameterization_name, save_intermediate_outputs):
    """Weight soil parameters for each hillslope based on the intersection of hillslopes and soils. 14 parameters are weighted.
    called in parameterize function."""
    
    # Step 1: read 2 tables    
    soils_table = os.path.join(workspace, "parameters_soil_weighted_by_component")
    df_soils = pd.DataFrame(arcpy.da.TableToNumPyArray(soils_table, "*"))
    df_soils = df_soils[(df_soils["DelineationName"] == delineation_name) &  
                        (df_soils["DiscretizationName"] == discretization_name) &
                        (df_soils["ParameterizationName"] == parameterization_name)]
    
    intersection_table = os.path.join(workspace, f"{discretization_name}_MUPOLYGON_intersection")
    df_intersections = pd.DataFrame(arcpy.da.TableToNumPyArray(intersection_table, ["HillslopeID", "MUKEY", "Shape_Area"])) 

    # Step 2: Merge intersection polygons with soils
    df_soils.MapUnitKey = df_soils.MapUnitKey.astype(str)
    df_intersections.MUKEY = df_intersections.MUKEY.astype(str)
    # here to assign values so it won't be NaN #TODO: add a warning or error if there are missing_mukeys
    missing_mukeys = df_intersections[~df_intersections["MUKEY"].isin(df_soils["MapUnitKey"])].MUKEY.unique()
    
    df_intersections_soils = pd.merge(df_intersections, df_soils, left_on="MUKEY", right_on="MapUnitKey", how="left")
    
    # Step 3: Weight soil parameters by area fractions
    parameters = ["Ksat", "G", "Porosity", "Rock", "Sand", "Silt", "Clay", "Splash", "Cohesion", "Pave", "SMax", "CV", "Distribution", "BPressure"]
    df_weighted_by_area = pd.DataFrame().assign(HillslopeID=df_intersections_soils.HillslopeID.unique())
    for hillsope_id in df_intersections_soils.HillslopeID.unique():
        # print(hillsope_id) ### remove this when testing is done
        df_hillslope = df_intersections_soils[df_intersections_soils.HillslopeID == hillsope_id]
        
        # For now: area with Pave = 1 will be excluded from the calculation
        pave_unique = df_hillslope.Pave.unique()
        if len(pave_unique) >= 2:
            df_hillslope = df_hillslope[df_hillslope.Pave != 1]
        
        #TODO: will there be a case where Pave=0 but Sand, Clay and Silt are all 0?

        total_area = df_hillslope.Shape_Area.sum()        
        for param in parameters:
            weighted_value = (df_hillslope[param] * df_hillslope.Shape_Area).sum() / total_area
            df_weighted_by_area.loc[df_weighted_by_area.HillslopeID == hillsope_id, param] = weighted_value

    return df_weighted_by_area


def extract_parameters(prjgdb, delineation_name, discretization_name, parameterization_name):
    """Extract parameters from two metatables. Called in parameterize function. Also convert strings to numbers if needed.
    called in parameterize function."""
    
    meta_parameterization_table = os.path.join(prjgdb, "metaParameterization")
    df_parameterization = pd.DataFrame(arcpy.da.TableToNumPyArray(meta_parameterization_table,"*"))
    df_parameterization = df_parameterization[(df_parameterization["DelineationName"] == delineation_name) &
                                            (df_parameterization["DiscretizationName"] == discretization_name) &
                                            (df_parameterization["ParameterizationName"] == parameterization_name)].squeeze()
    if df_parameterization.empty:
        raise Exception(f"No parameterization found for the given delineation, discretization, and parameterization names.")  
    max_thickness = int(df_parameterization["MaxThickness"])
    max_horizons = int(df_parameterization["MaxHorizons"])
    land_cover = df_parameterization["LandCoverPath"]
    land_cover_lut = df_parameterization["LandCoverLookUpTablePath"]
    soil_feature_class_path = df_parameterization["SoilsPath"]
    channel_type = df_parameterization["ChannelType"]
    soil_feature_class_path = df_parameterization["SoilsPath"]
    soils_database_path = df_parameterization["SoilsDatabasePath"]

    meta_workspace_table = os.path.join(prjgdb, "metaWorkspace")
    if arcpy.Exists(meta_workspace_table):
        df_workspace = pd.DataFrame(arcpy.da.TableToNumPyArray(meta_workspace_table, "*"))
        AGWA_directory = df_workspace["AGWADirectory"].values[0]
    else:
        raise Exception(f"The table 'metaWorkspace' does not exist in the workspace {prjgdb}.")
   
    return (max_thickness, max_horizons, land_cover, land_cover_lut, soil_feature_class_path, soils_database_path,
             AGWA_directory, channel_type)



def copy_parameterization(workspace, delineation_name, discretization_name, previous_parameterization_name, parameterization_name):
    
    """Copy parameterization from previous to new parameterization. Called in parameterize function.
    Note: element parameterization should be done before this step. Therefore, all element parameters should be kept intact for 
    the targe parameterization, and do not copy them from the previous parameterization.
    """


    tables = ["parameters_hillslopes", "parameters_channels"]
    index_fields = ["HillslopeID", "ChannelID"]
    hillslope_fields_copy = ["Ksat", "G", "Porosity", "Rock", "Sand", "Silt", "Clay", "Splash", "Cohesion", "Pave", "SMax", "CV", 
                        "Distribution", "BPressure", "Canopy", "Interception", "Manning", "Imperviousness"]
    channel_feilds_copy = ["Ksat", "Manning", "Pave", "Imperviousness", "SMax", "CV", "G", "Porosity", 
                      "Rock", "Sand", "Silt", "Clay", "Splash", "Cohesion", "Distribution", "BPressure", "Woolhiser"]

    
    for table, fields_to_copy, index_field in zip(tables, [hillslope_fields_copy, channel_feilds_copy], index_fields):

        try:
            table_path = arcpy.os.path.join(workspace, table)
            field_objects = arcpy.ListFields(table_path)
            all_fields = [field.name for field in field_objects if field.type != 'OID']
            cols_to_load = [index_field] + fields_to_copy + ["DelineationName", "DiscretizationName", "ParameterizationName"]
            df = pd.DataFrame(arcpy.da.TableToNumPyArray(table_path, cols_to_load))
            
            previous_data_set = df[(df["DelineationName"] == delineation_name) & 
                                   (df["DiscretizationName"] == discretization_name) &
                                   (df["ParameterizationName"] == previous_parameterization_name)]
            previous_data_set = previous_data_set.set_index(index_field)[fields_to_copy].to_dict(orient='index')

            field_indices = {field: all_fields.index(field) for field in fields_to_copy}

            where_clause = (f"DelineationName = '{delineation_name}' AND "
                            f"DiscretizationName = '{discretization_name}' AND "
                            f"ParameterizationName = '{parameterization_name}'")

            with arcpy.da.UpdateCursor(table_path, all_fields, where_clause) as cursor:
                for row in cursor:
                    hillslope_id = row[0]
                    if hillslope_id in previous_data_set:
                        for field in fields_to_copy:
                            row[field_indices[field]] = previous_data_set[hillslope_id][field]
                        cursor.updateRow(row)
            tweet(f"Update complete for table {table}.")
        except Exception as e:
            tweet(f"Failed to update table {table} due to error: {e}")

