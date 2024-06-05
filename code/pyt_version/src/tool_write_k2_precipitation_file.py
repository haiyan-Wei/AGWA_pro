import os
import re
import sys
import arcpy
import importlib
sys.path.append(os.path.dirname(__file__))
import code_write_k2_precipitation_file as agwa
importlib.reload(agwa)


class WriteK2PrecipitationFile(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 6 - Write K2 Precipitation File"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):

        """Define parameter definitions"""

        param0 = arcpy.Parameter(displayName="AGWA Delineation",
                                 name="AGWA_Delineation",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
        delineation_list = []
        project = arcpy.mp.ArcGISProject("CURRENT")
        m = project.activeMap
        for table in m.listTables():
            if table.name == "metaDelineation":
                with arcpy.da.SearchCursor(table, "DelineationName") as cursor:
                    for row in cursor:
                        delineation_list.append(row[0])
                break
        param0.filter.list = delineation_list

        param1 = arcpy.Parameter(displayName="AGWA Discretization",
                                 name="AGWA_Discretization",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")

        # TODO: Add NOAA Atlas 14 web scraping as an option for creating precipitation file
        # FAQ with NOAA's position on web scraping in question 2.5
        # https://www.weather.gov/owp/hdsc_faqs
        # Example web scraping request
        # https://hdsc.nws.noaa.gov/cgi-bin/hdsc/new/cgi_readH5.py?lat=37.4000&lon=-119.2000&type=pf&data=depth&units=english&series=pds

        param2 = arcpy.Parameter(displayName="Depth (mm)",
                                 name="Depth",
                                 datatype="GPDouble",
                                 parameterType="Required",
                                 direction="Input")
        param2.filter.type = "Range"
        param2.filter.list = [0, sys.float_info.max]

        param3 = arcpy.Parameter(displayName="Duration (hours)",
                                 name="Duration",
                                 datatype="GPDouble",
                                 parameterType="Required",
                                 direction="Input")
        param3.filter.type = "Range"
        param3.filter.list = [0.05, sys.float_info.max]

        param4 = arcpy.Parameter(displayName="Time Step Duration (minutes)",
                                 name="Time_step_duration",
                                 datatype="GPDouble",
                                 parameterType="Required",
                                 direction="Input")
        param4.filter.type = "Range"
        param4.filter.list = [1, sys.float_info.max]

        param5 = arcpy.Parameter(displayName="Hyetograph Shape",
                                 name="Hyetograph_Shape",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")

        param6 = arcpy.Parameter(displayName="Initial Soil Moisture (unit: fraction)",
                                 name="Initial Soil Moisture",
                                 datatype="GPDouble",
                                 parameterType="Required",
                                 direction="Input")
        param6.filter.type = "Range"
        param6.filter.list = [0, 1]

        param7 = arcpy.Parameter(displayName="Filename",
                                 name="Filename",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")

        param8 = arcpy.Parameter(displayName="Environment",
                                 name="Environment",
                                 datatype="GpString",
                                 parameterType="Optional",
                                 direction="Input")
        param8.filter.list = ["ArcGIS Pro", "ArcMap", "Geoprocessing Service"]
        param8.value = param8.filter.list[0]

        param9 = arcpy.Parameter(displayName="Workspace",
                                 name="Workspace",
                                 datatype="GPString",
                                 parameterType="Derived",
                                 direction="Output")
        
        param10 = arcpy.Parameter(displayName="Project GeoDataBase",
                                 name="ProjectGeoDataBase",
                                 datatype="GPString",
                                 parameterType="Derived",
                                 direction="Output")                               

        param11 = arcpy.Parameter(displayName="Debug messages",
                                 name="Debug",
                                 datatype="GPString",
                                 parameterType="Optional",
                                 direction="Input")
 
        params = [param0, param1, param2, param3, param4, param5, param6, param7, param8, param9, param10, param11]
        return params


    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True
    

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        agwa_directory, workspace, prjgdb, discretization_list = "", "", "", []
        if parameters[0].value:
            delineation_name = parameters[0].valueAsText
            project = arcpy.mp.ArcGISProject("CURRENT")
            m = project.activeMap
            for table in m.listTables():
                if table.name == "metaDelineation":
                    with arcpy.da.SearchCursor(table, ["DelineationName", "ProjectGeoDataBase", 
                                                    "DelineationWorkspace"]) as cursor:
                        for row in cursor:
                            if row[0] == delineation_name:
                                prjgdb = row[1]
                                workspace = row[2]
                                if prjgdb and workspace:
                                    break                                

            for table in m.listTables():                    
                if table.name == "metaWorkspace":
                    with arcpy.da.SearchCursor(table, ["AGWADirectory", "ProjectGeoDataBase"]) as cursor:
                        for row in cursor:
                            if row[1] == prjgdb:
                                agwa_directory = row[0]
                        break

            for table in m.listTables():
                if table.name == "metaDiscretization":
                    with arcpy.da.SearchCursor(table, ["DelineationName", "DiscretizationName"]) as cursor:
                        for row in cursor:
                            if row[0] == delineation_name:
                                discretization_list.append(row[1])
                        break

        # param3 should be integer values only but is GPDouble instead of GPLong because
        #  the toolbox UI for a GPLong with a range is not consistent with other numeric inputs
        #  so round the input in the event the user entered a decimal number
        parameters[1].filter.list = discretization_list
        if parameters[4].value:
            parameters[4].value = round(parameters[4].value)

        distributions_list = []
        if agwa_directory:
            precip_distribution_table = os.path.join(agwa_directory, "lookup_tables.gdb", "precipitation_distributions_LUT")
            if arcpy.Exists(precip_distribution_table):
                field_names = [f.name for f in arcpy.ListFields(precip_distribution_table)]
                distributions_list = field_names[2:]

        parameters[5].filter.list = distributions_list
        parameters[9].value = workspace
        parameters[10].value = prjgdb

        return


    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        if parameters[0].value and parameters[1].value and parameters[7].value:
            delineation_name = parameters[0].valueAsText
            discretization_name = parameters[1].valueAsText
            precipitation_name = parameters[7].valueAsText
            project = arcpy.mp.ArcGISProject("CURRENT")
            m = project.activeMap
            for table in m.listTables():
                if table.name == "metaK2PrecipitationFile":
                    with arcpy.da.SearchCursor(table, ["DelineationName", "DiscretizationName", 
                                                    "PrecipitationName"]) as cursor:
                        for row in cursor:
                            if ((row[0] == delineation_name) and (row[1] == discretization_name) and 
                                (row[2] == precipitation_name)):
                                parameters[7].setErrorMessage("Precipitation file already exists for this delineation and discretization")

        return


    def execute(self, parameters, messages):
        """The source code of the tool."""
        # arcpy.AddMessage("Toolbox source: " + os.path.dirname(__file__))
        arcpy.AddMessage("Script source: " + __file__)

        delineation_par = parameters[0].valueAsText
        discretization_par = parameters[1].valueAsText
        depth_par = parameters[2].valueAsText
        duration_par = parameters[3].valueAsText
        time_step_par = parameters[4].valueAsText
        hyetograph_par = parameters[5].valueAsText
        soil_moisture_par = parameters[6].valueAsText
        filename_par = parameters[7].valueAsText
        environment_par = parameters[8].valueAsText
        workspace_par = parameters[9].valueAsText
        prjgdb_par = parameters[10].valueAsText

        agwa.initialize_workspace(prjgdb_par, delineation_par, discretization_par, depth_par, duration_par, time_step_par,
                                  hyetograph_par, soil_moisture_par, filename_par)
        
        agwa.write_precipitation(prjgdb_par, workspace_par, delineation_par, discretization_par, filename_par)

        return

    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return
