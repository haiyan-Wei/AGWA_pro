import arcpy
import os
import sys
import pandas as pd
import glob
import subprocess
sys.path.append(os.path.dirname(__file__))
import code_view_results as agwa
import importlib
importlib.reload(agwa)

class ViewK2Results(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 11 - Riew K2 Simulation"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        param0 = arcpy.Parameter(displayName="AGWA Discretization",
                                 name="AGWA_Discretization",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
        discretization_list = []
        project = arcpy.mp.ArcGISProject("CURRENT")
        m = project.activeMap
        for lyr in m.listLayers():
            if lyr.isFeatureLayer:
                if lyr.supports("CONNECTIONPROPERTIES"):
                    cp = lyr.connectionProperties
                    wf = cp.get("workspace_factory")
                    if wf == "File Geodatabase":
                        ci = cp.get("connection_info")
                        if ci:
                            workspace = ci.get("database")
                            if workspace:
                                meta_discretization_table = os.path.join(workspace, "metaDiscretization")
                                if arcpy.Exists(meta_discretization_table):
                                    dataset_name = cp["dataset"]
                                    discretization_name = dataset_name.replace("_elements", "")
                                    fields = ["DiscretizationName"]
                                    row = None
                                    expression = "{0} = '{1}'".format(
                                        arcpy.AddFieldDelimiters(workspace, "DiscretizationName"), discretization_name)
                                    with arcpy.da.SearchCursor(meta_discretization_table, fields, expression) as cursor:
                                        for row in cursor:
                                            discretization_name = row[0]
                                            discretization_list.append(discretization_name)

        param0.filter.list = discretization_list

        param1 = arcpy.Parameter(displayName="Simulation",
                                 name="Simulation",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")

        param2 = arcpy.Parameter(displayName="Unit",
                                 name="Unit",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
        param2.filter.list = ["Metric"]

        param3 = arcpy.Parameter(displayName="Output",
                                 name="Output",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
        param3.filter.list = ["Infiltration (mm)", "Runoff (mm)", "Runoff (m^3)", 
                              "Sediment Yield (kg/ha)", "Peak Flow (mm/hr)", 
                              "Peak Flow (m^3/s)", "Peak Sediment Discharge (kg/s)"]

        param4 = arcpy.Parameter(displayName="Workspace",
                                 name="Workspace",
                                 datatype="GPString",
                                 parameterType="Derived",
                                 direction="Output")

        param5 = arcpy.Parameter(displayName="Debug messages",
                                 name="Debug",
                                 datatype="GPString",
                                 parameterType="Optional",
                                 direction="Input")

        param6 = arcpy.Parameter(displayName="Save Intermediate Outputs",
                                 name="Save_Intermediate_Outputs",
                                 datatype="GPBoolean",
                                 parameterType="Optional",
                                 direction="Input")
        param6.value = False

        params = [param0, param1, param2, param3, param4, param5, param6]
        return params


    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True


    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        discretization_name = parameters[0].value
        workspace = ""
        if discretization_name:
            project = arcpy.mp.ArcGISProject("CURRENT")
            m = project.activeMap
            for lyr in m.listLayers():
                if lyr.isFeatureLayer:
                    if lyr.supports("CONNECTIONPROPERTIES"):
                        cp = lyr.connectionProperties
                        wf = cp.get("workspace_factory")
                        if wf == "File Geodatabase":
                            dataset_name = cp["dataset"]
                            if dataset_name == discretization_name + "_elements":
                                ci = cp.get("connection_info")
                                if ci:
                                    workspace = ci.get("database")
        
        parameters[4].value = workspace
        workspace_directory = os.path.split(workspace)[0]

        # populate the available parameter files
        simulations_list = []
        if parameters[0].value:
            discretization_name = parameters[0].valueAsText

            meta_discretization_table = os.path.join(workspace, "metaDiscretization")
            if arcpy.Exists(meta_discretization_table):
                df_discretization = pd.DataFrame(arcpy.da.TableToNumPyArray(meta_discretization_table,
                                                                            ["DelineationName", "DiscretizationName"]))
                df_discretization_filtered = \
                    df_discretization[df_discretization.DiscretizationName == discretization_name]
                delineation_name = df_discretization_filtered.DelineationName.values[0]        

                simulations_path = os.path.join(workspace_directory, delineation_name, discretization_name,
                                                "simulations", "*")
                simulations_list = glob.glob(simulations_path)

        parameters[1].filter.list = simulations_list

        return


    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        # arcpy.AddMessage("Toolbox source: " + os.path.dirname(__file__))
        arcpy.AddMessage("Script source: " + __file__)
        discretization_par = parameters[0].valueAsText
        simulation_par = parameters[1].valueAsText
        unit_par = parameters[2].valueAsText
        output_par = parameters[3].valueAsText
        workspace_par = parameters[4].valueAsText       
        workspace_directory = os.path.split(workspace_par)[0]       

        for v in [discretization_par, simulation_par, unit_par, output_par, workspace_par, workspace_directory]:
            arcpy.AddMessage(v)
        
        agwa.view_k2_results(discretization_par, simulation_par, unit_par, output_par, workspace_par)

        return


    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return
