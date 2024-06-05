import re
import os
import sys
import arcpy
sys.path.append(os.path.dirname(__file__))
import code_create_postfire_land_cover as agwa
import importlib
importlib.reload(agwa)


class CreatePostfireLandCover(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Create Post-fire Land Cover"
        self.description = ""
        self.category = "Land Cover Tools"
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
                
        param1 = arcpy.Parameter(displayName="Burn Severity Map",
                                 name="Burn_Severity_Map",
                                 datatype=["GPFeatureLayer", "GPRasterLayer"],
                                 parameterType="Required",
                                 direction="Input")

        param2 = arcpy.Parameter(displayName="Severity Field",
                                 name="Severity_Field",
                                 datatype="Field",
                                 parameterType="Required",
                                 direction="Input")
        param2.parameterDependencies = [param1.name]

        param3 = arcpy.Parameter(displayName="Pre-fire Land Cover Raster",
                                 name="Land_Cover_Raster",
                                 datatype="GPRasterLayer",
                                 parameterType="Required",
                                 direction="Input")

        param4 = arcpy.Parameter(displayName="Land Cover Modification Table",
                                    name="Land_Cover_modification_Table",
                                    datatype="GPString",
                                    parameterType="Required",
                                    direction="Input")
        param4.filter.list = ['mrlc1992_severity', 'mrlc2001_severity']
        
        param5 = arcpy.Parameter(displayName="Workspace",
                                 name="Workspace",
                                 datatype="DEWorkspace",
                                 parameterType="Derived",
                                 direction="Input")

        param6 = arcpy.Parameter(displayName="Project Geodatabase",
                                 name="Workspace",
                                 datatype="DEWorkspace",
                                 parameterType="Derived",
                                 direction="Input")

        param7 = arcpy.Parameter(displayName="Directory For Post-fire Land Cover",
                                name="Output_Location",
                                datatype="DEWorkspace",
                                parameterType="Optional",
                                direction="Input")
        param7.enabled = False
        
        param8 = arcpy.Parameter(displayName="Post-fire Land Cover File Name",
                                 name="Output_Name",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
        
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
            delineation_name = parameters[0].valueAsText
            workspace, prjgdb = self.get_workspace_discretization_list(delineation_name)            
            parameters[5].value = workspace
            parameters[6].value = prjgdb
            
        return

    def updateMessages(self, parameters):
        if parameters[7].altered:
            lancover_name = parameters[7].valueAsText
            lancover_name = lancover_name.strip()
            if re.match("^[A-Za-z][A-Za-z0-9_]*$", lancover_name) is None:
                parameters[3].setErrorMessage("The land cover name must start with a letter and contain only letters, numbers, and underscores.")
    
 
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
                                
        return workspace, prjgdb


    def execute(self, parameters, messages):
        """The source code of the tool."""
        # arcpy.AddMessage("Toolbox source: " + os.path.dirname(__file__))
        arcpy.AddMessage("Script source: " + __file__)
        burn_severity = parameters[1].valueAsText
        severity_field = parameters[2].valueAsText
        land_cover = parameters[3].valueAsText
        change_table = parameters[4].valueAsText
        workspace = parameters[5].valueAsText
        prjgdb = parameters[6].valueAsText

        output_location = os.path.join(os.path.split(workspace)[0], "postfire_land_cover")
        if not os.path.exists(output_location):
            os.makedirs(output_location)
        output_name = parameters[8].valueAsText

        agwa.execute(workspace, prjgdb, burn_severity, severity_field, land_cover, change_table, 
                     output_location, output_name)
        return

    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return
