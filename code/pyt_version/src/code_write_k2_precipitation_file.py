import os
import arcpy
import math
import datetime
import numpy as np
import pandas as pd
import arcpy.management
from pathlib import Path
from arcpy._mp import Table


Prop_xcoord = "xcoord" #???
Prop_ycoord = "ycoord"


def tweet(msg):
    """Produce a message for both arcpy and python"""
    m = "\n{}\n".format(msg)
    arcpy.AddMessage(m)
    print(arcpy.GetMessages())


def initialize_workspace(prjgdb, delineation_name, discretization, depth, duration, time_step, hyetograph_shape, soil_moisture,
                         precipitation_name):

    tweet("Creating metaPrecipitationFile if it does not exist")    
    meta_precipitation_table = os.path.join(prjgdb, "metaK2PrecipitationFile")
    fields = ["DelineationName", "DiscretizationName", "PrecipitationName", "Depth", "Duration",
              "TimeStep", "HyetographShape", "InitialSoilMoisture", "CreationDate", "AGWAVersionAtCreation",
              "AGWAGDBVersionAtCreation"]
    if not arcpy.Exists(meta_precipitation_table):
        arcpy.CreateTable_management(prjgdb, "metaK2PrecipitationFile") 
        for field in fields:
            arcpy.AddField_management(meta_precipitation_table, field, "TEXT")
    
    tweet("Documenting precipitation parameters to metadata")
    with arcpy.da.InsertCursor(meta_precipitation_table, fields) as cursor:
        cursor.insertRow((delineation_name, discretization, precipitation_name, depth, duration, time_step,
                        hyetograph_shape, soil_moisture, datetime.datetime.now().isoformat(), "4.0", "4.0"))
            
    tweet("Adding metaK2PrecipitationFile table to the map")
    aprx = arcpy.mp.ArcGISProject("CURRENT")
    map = aprx.activeMap
    for t in map.listTables():
        if t.name == "metaK2PrecipitationFile":
            map.removeTable(t)
            break
    table = Table(meta_precipitation_table)
    map.addTable(table)


def write_precipitation(prjgdb, workspace, delineation, discretization, precipitation_name):
    """Write the precipitation file for the specified delineation and discretization."""

    tweet("Reading precipitation metadata")
    (depth, duration, time_step, hyetograph_shape, 
     soil_moisture, agwa_directory) = extract_parameters(prjgdb, delineation, discretization, precipitation_name)

    precip_distribution_file = os.path.join(agwa_directory, "lookup_tables.gdb", "precipitation_distributions_LUT")

    header = write_header(discretization, depth, duration, hyetograph_shape)
    body = write_from_distributions_lut(depth, duration, time_step, hyetograph_shape, soil_moisture,
                                        precip_distribution_file)
    output_directory = os.path.join(os.path.split(workspace)[0], 
                                    "modeling_files", discretization, "precipitation_files")
    Path(output_directory).mkdir(parents=True, exist_ok=True)
    output_filename = os.path.join(output_directory, precipitation_name + ".pre")
    output_file = open(output_filename, "w")
    output_file.write(header + body)
    output_file.close()
    tweet(f"Precipitation file '{precipitation_name}.pre' has been written to {output_directory}")


def write_header(discretization_base_name, depth, duration, storm_shape):
    header = ""
    header += f"! User-defined storm depth {depth}mm.\n"
    header += f"! Hyetograph computed using {storm_shape} distribution.\n"
    header += f"! Storm generated for the {discretization_base_name} discretization.\n"
    header += f"! Duration = {duration} hours.\n\n"

    return header


def write_from_distributions_lut(depth, duration, time_step_duration, hyetograph_shape, soil_moisture, precip_distribution_file,
                                 hillslope_id="notSet"):
    try:
        time_steps = math.floor((duration * 60 / time_step_duration) + 1)

        rg_line = "BEGIN RG1" + "\n"
        if not hillslope_id == "notSet":
            rg_line = "BEGIN RG" + hillslope_id + "\n"

        coordinate_line = "  X = " + \
                          str(Prop_xcoord) + ", Y = " + str(Prop_ycoord) + "\n"
        if (Prop_xcoord == "xcoord") or (Prop_ycoord == "ycoord"):
            coordinate_line = "  X = 0, Y = 0\n"

        soil_moisture_line = "  SAT = " + str(soil_moisture) + "\n"
        time_steps_line = "  N = " + str(time_steps) + "\n"
        header_line = "  TIME        DEPTH\n" + \
                      "! (min)        (mm)\n"
        design_storm = rg_line + coordinate_line + soil_moisture_line + time_steps_line + header_line

        fields = ["Time", hyetograph_shape]

        time = 0.0
        value = 0.0
        max_dif = 0.0
        t_start = 0.0
        t_end = 0.0
        p_start = 0.0
        p_end = 0.0

        dist_curs = arcpy.da.SearchCursor(precip_distribution_file, fields)
        for dist_row in dist_curs:
            time = dist_row[0]
            value = dist_row[1]
            new_time = time + duration
            if new_time <= 24:
                where_clause = "Time = " + str(new_time)

                upper_bound_curs = arcpy.da.SearchCursor(
                    precip_distribution_file, fields, where_clause)
                upper_bound_row = next(upper_bound_curs)
                upper_time = upper_bound_row[0]
                upper_value = upper_bound_row[1]
                difference = upper_value - value

                if difference > max_dif:
                    t_start = time
                    t_end = upper_time
                    p_start = value
                    p_end = upper_value
                    max_dif = difference

        the_kin_time = 0
        cum_depth = 0
        p_ratio = 0
        current_time = ""
        current_depth = ""

        for i in range(time_steps):
            the_time = t_start + i * time_step_duration / 60
            the_kin_time = i * time_step_duration
            p_ratio_query = "Time = " + str(round(the_time, 1))
            p_ratio_cursor = arcpy.da.SearchCursor(
                precip_distribution_file, fields, p_ratio_query)
            p_ratio_row = next(p_ratio_cursor)
            p_ratio = p_ratio_row[1]

            cum_depth = depth * (p_ratio - p_start) / (p_end - p_start)

            # Add the current line to the string
            current_time = "%.2f" % round(the_kin_time, 2)
            current_time = current_time.rjust(6, ' ')
            current_depth = "%.2f" % round(cum_depth, 2)
            current_depth = current_depth.rjust(13, ' ')
            design_storm += current_time + current_depth + "\n"

        # If the time step duration does not divide into the storm duration
        # evenly, this accounts for the remainder
        if int(float(current_time.strip())) < (duration * 60):
            current_time = "%.2f" % round(duration, 2)
            current_time = current_time.rjust(6, ' ')
            current_depth = "%.2f" % round(depth, 2)
            current_depth = current_depth.rjust(13, ' ')
            design_storm += current_time + current_depth + "\n"

        if (Prop_xcoord == "xcoord") and (Prop_ycoord == "ycoord"):
            design_storm += "END\n"
        else:
            design_storm += "END\n\n" + \
                            "BEGIN RG2\n" + \
                            "  X = " + str(Prop_xcoord) + ", Y = " + str(Prop_ycoord) + "\n" + \
                            "  SAT = " + str(soil_moisture) + "\n" + \
                            "  N = 1\n" + \
                            "  TIME        DEPTH\n" + \
                            "! (min)        (mm)\n" + \
                            "  0.00         0.00\n" + \
                            "END\n"

        return design_storm
    except BaseException:
        msg = "WriteFromDistributionsLUT() Error"
        tweet(msg)


def extract_parameters(prjgdb, delineation, discretization, precipitation_file):    

    # Check if the metaK2PrecipitationFile table exists
    meta_precipitation_table = os.path.join(prjgdb, "metaK2PrecipitationFile")
    fields = ["DelineationName", "DiscretizationName", "PrecipitationName", "Depth", "Duration",
              "TimeStep", "HyetographShape", "InitialSoilMoisture"]
    if not arcpy.Exists(meta_precipitation_table):
        raise Exception("Cannot proceed. \nThe table '{}' does not exist.".format(meta_precipitation_table))
    
    # Read the precipitation parameters from the metaK2PrecipitationFile table
    else:
        depth, duration, time_step, hyetograph_shape, soil_moisture = np.nan, np.nan, np.nan, None, np.nan
        with arcpy.da.SearchCursor(meta_precipitation_table, fields) as cursor:
            for row in cursor:
                if row[0] == delineation and row[1] == discretization and row[2] == precipitation_file:
                    depth = float(row[3])
                    duration = float(row[4])
                    time_step = int(row[5])
                    hyetograph_shape = row[6]
                    soil_moisture = float(row[7])
                    break
        if np.isnan(depth) or np.isnan(duration) or time_step is None or hyetograph_shape is None or np.isnan(soil_moisture):
            raise Exception("Cannot proceed. \nNo precipitation parameters found for this delineation and discretization in metaPrecipitationFile table.")
    
    # Read the AGWA directory from the metaWorkspace table
    meta_workspace_table = os.path.join(prjgdb, "metaWorkspace")
    df_meta_workspace = pd.DataFrame(arcpy.da.TableToNumPyArray(meta_workspace_table, '*'))
    agwa_directory = df_meta_workspace['AGWADirectory'].values[0]

    return depth, duration, time_step, hyetograph_shape, soil_moisture, agwa_directory