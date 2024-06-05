import os
import sys
import arcpy
import importlib
sys.path.append(os.path.dirname(__file__))
import code_plot_hydrograph as agwa
importlib.reload(agwa)

class PlotHydrograph(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 12 - Plot Hydrograph"
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

        param2 = arcpy.Parameter(displayName="Simulation",
                                 name="Simulation",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")

        param3 = arcpy.Parameter(displayName="Element Type",
                                 name="Elements",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
        param3.filter.list = ["Hillslope", "Channel"]
       
        param4 = arcpy.Parameter(displayName="Element ID",
                                 name="ElementID",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input",
                                 multiValue=True)
        param4.filter.type = 'ValueList'

        param5 = arcpy.Parameter(displayName="Multiple Elements In One Plot",
                                 name="Multiple_Elements_In_One_Plot",
                                 datatype="GPBoolean",
                                 parameterType="Optional",
                                 direction="Input")
        param5.enabled = False

        param6 = arcpy.Parameter(displayName="Unit",
                                 name="Unit",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
        param6.filter.list = ["Metric", "English"]

        param7 = arcpy.Parameter(displayName="Output Variable",
                                 name="Output",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
                                         
        param8 = arcpy.Parameter(displayName="Simulation Directory",
                                 name="Simulation_Directory",
                                 datatype="GPString",
                                 parameterType="Derived",
                                 direction="Output")

        param9 = arcpy.Parameter(displayName="Debug messages",
                                 name="Debug",
                                 datatype="GPString",
                                 parameterType="Optional",
                                 direction="Input")

        params = [param0, param1, param2, param3, param4, param5, param6, param7, param8, param9]
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
                    parameters[8].value = simulation_directory
                    simulations_list = [folder for folder in os.listdir(simulation_directory)
                                     if os.path.isdir(os.path.join(simulation_directory, folder))]
                    parameters[2].filter.list = simulations_list
                else:
                    parameters[2].filter.list = []

        # Populate the element ID list
        if parameters[3].altered:
            parameters[4].filter.list = []
            discretization = parameters[1].valueAsText
            element_type = parameters[3].valueAsText
            element_list = []
            if element_type == 'Hillslope':
                element_feature_class = os.path.join(workspace, f"{discretization}_hillslopes")
                with arcpy.da.SearchCursor(element_feature_class, "HillslopeID") as cursor:
                    element_list = [str(row[0]) for row in cursor]

            if element_type == 'Channel':
                element_feature_class = os.path.join(workspace, f"{discretization}_channels")
                with arcpy.da.SearchCursor(element_feature_class, "ChannelID") as cursor:
                    element_list = [str(row[0]) for row in cursor]
            parameters[4].filter.list = [int(item) for item in element_list]
            if len(element_list) > 0:
                parameters[5].enabled = True

        # Populate the output vaiables
        if parameters[6].altered:
            parameters[7].filter.list = []
            if parameters[6].valueAsText == 'Metric':
                parameters[7].filter.list = ["Rainfall Rate (mm/hr)", "Runoff Rate (mm/hr)", "Runoff Rate (m³/s)", "Total Sediment Yield (kg/s)"]
            if parameters[6].valueAsText == 'English':
                parameters[7].filter.list = ["Rainfall Rate (in/hr)", "Runoff Rate (in/hr)", "Runoff Rate (ft³/s)", "Total Sediment Yield (lb/s)"]

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

        return
    
    
    def execute(self, parameters, messages):
        """The source code of the tool."""
        # arcpy.AddMessage("Toolbox source: " + os.path.dirname(__file__))
        arcpy.AddMessage("Script source: " + __file__)

        delineation = parameters[0].valueAsText
        discretization = parameters[1].valueAsText
        simulation = parameters[2].valueAsText
        element_type = parameters[3].valueAsText
        elementid_list = parameters[4].valueAsText
        multiple_elements = parameters[5].value
        unit = parameters[6].valueAsText
        output_variable = parameters[7].valueAsText
        simulation_directory = parameters[8].valueAsText         

        elementid_list = elementid_list.split(';')
        elementid_list = [int(id_str) for id_str in elementid_list if id_str.isdigit()]

        agwa.plot_hydrograph(simulation, element_type, elementid_list, multiple_elements, output_variable, simulation_directory, unit)     

        return

    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return
