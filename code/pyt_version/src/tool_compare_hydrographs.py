import os
import sys
import arcpy
import importlib
sys.path.append(os.path.dirname(__file__))
import code_compare_hydrographs as agwa
importlib.reload(agwa)

class CompareHydrographs(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 14 - Compare Hydrographs"
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

        param2 = arcpy.Parameter(displayName="Simulations to Compare",
                                 name="Simulations",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input",
                                 multiValue=True)
        param2.filter.type = 'ValueList'

        param3 = arcpy.Parameter(displayName="Hillslope Feature Class",
                                 name="Hillslope_Feature_Class",
                                 datatype="GPFeatureLayer",
                                 parameterType="Optional",
                                 direction="Input")

        param4 = arcpy.Parameter(displayName="HillslopeID List",
                                 name="HillslopeID_List",
                                 datatype="GPString",
                                 parameterType="Optional",
                                 direction="Input")        
        param4.parameterDependencies = [param3.name]
       
        param5 = arcpy.Parameter(displayName="Channel Feature Class",
                                 name="Channel_Feature_Class",
                                datatype="GPFeatureLayer",
                                parameterType="Optional",
                                direction="Input")
        param4.parameterDependencies = [param3.name]

        param6 = arcpy.Parameter(displayName="ChannelID List",
                                    name="ChannelID_List",
                                    datatype="GPString",
                                    parameterType="Optional",
                                    direction="Input")
        
        param7 = arcpy.Parameter(displayName="Unit",
                                 name="Unit",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
        param7.filter.list = ["Metric", "English"]

        param8 = arcpy.Parameter(displayName="Output Variable",
                                 name="Output",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
                                         
        param9 = arcpy.Parameter(displayName="Simulation Directory",
                                 name="Simulation_Directory",
                                 datatype="GPString",
                                 parameterType="Derived",
                                 direction="Output")

        param10 = arcpy.Parameter(displayName="Debug messages",
                                 name="Debug",
                                 datatype="GPString",
                                 parameterType="Optional",
                                 direction="Input")

        params = [param0, param1, param2, param3, param4, param5, param6, param7, param8, param9, param10]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""


        if parameters[0].altered:
            workspace = ""
            delineation_name = parameters[0].valueAsText
            workspace, _, discretization_list = self.get_workspace_discretization_list(delineation_name)
            parameters[1].filter.list = discretization_list

            # populate the available parameter files
            simulations_list = []
            if parameters[1].value:
                discretization_name = parameters[1].valueAsText
                simulation_directory = os.path.join(os.path.split(workspace)[0], "modeling_files", discretization_name, "simulations")
                if os.path.exists(simulation_directory):
                    simulations_list = [folder for folder in os.listdir(simulation_directory)
                                     if os.path.isdir(os.path.join(simulation_directory, folder))]
                    parameters[9].value = simulation_directory
                    parameters[2].filter.list = simulations_list
                else:
                    parameters[2].filter.list = []

        hillslope_ids = []
        if parameters[3].altered:
            feature_class = parameters[3].valueAsText
            try:            
                with arcpy.da.SearchCursor(feature_class, ["HillslopeID"]) as cursor:
                    for row in cursor:
                        hillslope_ids.append(row[0])
                parameters[4].value = ";".join([str(id) for id in hillslope_ids])
            except:
                pass

        channel_ids = []
        if parameters[5].altered:
            feature_class = parameters[5].valueAsText
            try:
                with arcpy.da.SearchCursor(feature_class, ["ChannelID"]) as cursor:
                    for row in cursor:
                        channel_ids.append(row[0])
                parameters[6].value = ";".join([str(id) for id in channel_ids])
            except:
                pass
                
        # Populate the output vaiables
        if parameters[7].altered:
            parameters[8].filter.list = []
            if parameters[7].valueAsText == 'Metric':
                parameters[8].filter.list = ["Rainfall Rate (mm/hr)", "Runoff Rate (mm/hr)", 
                                             "Runoff Rate (m³/s)", "Total Sediment Yield (kg/s)"]
            if parameters[7].valueAsText == 'English':
                parameters[8].filter.list = ["Rainfall Rate (in/hr)", "Runoff Rate (in/hr)", 
                                             "Runoff Rate (ft³/s)", "Total Sediment Yield (lb/s)"]

        if not parameters[3].value:
            parameters[4].value = "no Hillslope Id selected"
        if not parameters[5].value:
            parameters[6].value = "no Channel Id selected"

    def get_workspace_discretization_list(self, delineation_name):
        """Retrieve delineation information from metaDelineation table."""
        workspace, discretization_list = "", []
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

        for table in m.listTables():
            if table.name == "metaDiscretization":
                with arcpy.da.SearchCursor(table, ["DelineationName", "DiscretizationName"]) as cursor:
                    for row in cursor:
                        if row[0] == delineation_name:
                            discretization_list.append(row[1])
                    break

        return workspace, prjgdb, discretization_list
    

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        if parameters[0].value and parameters[2].filter.list == []:
            parameters[1].setErrorMessage("No discretization found for the selected delineation.")

        if parameters[3].value:
            hillslope_feature_class = parameters[3].valueAsText
            if not arcpy.ListFields(hillslope_feature_class, "HillslopeID"):
                parameters[3].setErrorMessage("Hillslope Feature Class must have a field named 'HillslopeID'.")
            elif not arcpy.Describe(hillslope_feature_class).FIDSet:
                parameters[3].setErrorMessage("No records selected in Hillslope Feature Class. Please select record(s) before proceeding.")
                                                
        if parameters[5].value:
            channel_feature_class = parameters[5].valueAsText
            if not arcpy.ListFields(channel_feature_class, "ChannelID"):
                parameters[5].setErrorMessage("Channel Feature Class must have a field named 'ChannelID'.")
            elif not arcpy.Describe(channel_feature_class).FIDSet:
                parameters[5].setErrorMessage("No records selected in Channel Feature Class. Please select record(s) before proceeding.")
                

        return
    

    def execute(self, parameters, messages):
        """The source code of the tool."""

        arcpy.AddMessage("Script source: " + __file__)

        delineation = parameters[0].valueAsText
        discretization = parameters[1].valueAsText
        simulation_list = parameters[2].valueAsText
        hillslope_feature_class = parameters[3].valueAsText
        channel_feature_class = parameters[4].valueAsText
        hillslope_ids = parameters[5].valueAsText
        channel_ids = parameters[6].valueAsText
        unit = parameters[7].valueAsText
        output_variable = parameters[8].valueAsText
        simulation_directory = parameters[9].valueAsText         

        hillslope_ids = hillslope_ids.split(';')
        channel_ids = channel_ids.split(';')
        simulation_list = simulation_list.split(';')

        hillslope_ids = [int(id_str) for id_str in hillslope_ids if id_str.isdigit()]
        channel_ids = [int(id_str) for id_str in channel_ids if id_str.isdigit()]

        agwa.plot_hydrographs(simulation_list, hillslope_ids, channel_ids, output_variable, simulation_directory, unit)     

        return

    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return

