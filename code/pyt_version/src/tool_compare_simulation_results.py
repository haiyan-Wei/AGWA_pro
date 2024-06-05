import os
import re
import sys
import arcpy
import importlib
sys.path.append(os.path.dirname(__file__))
import code_compare_simulation_results as agwa
importlib.reload(agwa)


class CompareSimulationResults(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 13 - Compare Simulation Results"
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

        param2 = arcpy.Parameter(displayName="Method",
                                 name="Compare_Method",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
        param2.filter.list = ["Relative Difference (%)", "Absolute Difference"]

        param3 = arcpy.Parameter(displayName="Base Simulations",
                                 name="Base_Joins",
                                 datatype="GPString",
                                 parameterType="Required",
                                 direction="Input")
        
        param4 = arcpy.Parameter(displayName="Target Simulations",
                            name="Existing_Joins",
                            datatype="GPString",
                            parameterType="Required",
                            direction="Input")
        
        param5 = arcpy.Parameter(displayName="Use Default Comparison Name",
                                    name="Use_Default_Comparison_Name",
                                    datatype="GPBoolean",
                                    parameterType="Optional",
                                    direction="Input")
        
        param6 = arcpy.Parameter(displayName="Comparison Name",
                                 name="Comparison_Name",
                                 datatype="GPString",
                                 parameterType="Optional",
                                 direction="Input")

        param7 = arcpy.Parameter(displayName="Workspace",
                                 name="Workspace",
                                 datatype="GPString",
                                 parameterType="Derived",
                                 direction="Output")

        param8 = arcpy.Parameter(displayName="Debug messages",
                                 name="Debug",
                                 datatype="GPString",
                                 parameterType="Optional",
                                 direction="Input")
 
        params = [param0, param1, param2, param3, param4, param5, param6, param7, param8]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        # set the workspace parameter based on the selected discretization
        workspace, prjgdb, discretization_list = "", "", []
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
                if table.name == "metaDiscretization":
                    with arcpy.da.SearchCursor(table, ["DelineationName", "DiscretizationName"]) as cursor:
                        for row in cursor:
                            if row[0] == delineation_name:
                                discretization_list.append(row[1])
                        break
        
        parameters[1].filter.list = discretization_list
        parameters[7].value = workspace

        # Populate the list of simulations that can be joined
        simulation_list = []
        if parameters[0].value and parameters[1].value:
            discretization_name = parameters[1].valueAsText
            simulation_directory = os.path.join(os.path.split(workspace)[0], "modeling_files", discretization_name, "simulations")
            if os.path.exists(simulation_directory):
                simulations_list = [folder for folder in os.listdir(simulation_directory)
                                     if os.path.isdir(os.path.join(simulation_directory, folder))]
                for simulation in simulations_list:
                    results_gdb_table = os.path.join(simulation_directory, simulation, simulation + "_results.gdb", "k2_results")
                    if arcpy.Exists(results_gdb_table):
                        simulation_list.append(simulation)
                parameters[3].filter.list = simulation_list
                parameters[4].filter.list = simulation_list

            else:
                parameters[3].filter.list = []
                parameters[4].filter.list = []

        # Remove the base simulation from the target simulation list and vice versa, so that the user cannot select the same simulation for both
        if parameters[0].value and parameters[1].value and parameters[3].value:
            base_simulation = parameters[3].valueAsText            
            parameters[4].filter.list = [simulation for simulation in parameters[4].filter.list if simulation != base_simulation]

        if parameters[0].value and parameters[1].value and parameters[4].value:
            target_simulation = parameters[4].valueAsText
            parameters[3].filter.list = [simulation for simulation in parameters[3].filter.list if simulation != target_simulation]

            
        if parameters[2].value and parameters[3].value and parameters[4].value:
            method = parameters[2].valueAsText
            base_simulation = parameters[3].valueAsText
            target_simulation = parameters[4].valueAsText
            if parameters[5].altered and parameters[5].value:
                parameters[6].value = f"{target_simulation}_{base_simulation}_{method[:3]}"     

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        simulation_list = parameters[3].filter.list
        if len(simulation_list) == 0:
            parameters[1].setErrorMessage("No simulations are available for comparison. Please run a simulation first.")
        if not parameters[4].value and len(parameters[3].filter.list) == 1:
            parameters[1].setErrorMessage("Only one simulation is available. Cannot compare. Please run another simulation first.")
        if parameters[3].value and len(parameters[4].filter.list) == 0:
            parameters[1].setErrorMessage("Only one simulation is available. Cannot compare. Please run another simulation first.")

        if parameters[6].value:
            comparison_name = parameters[6].valueAsText
            comparison_name = comparison_name.strip()
            if re.match("^[A-Za-z][A-Za-z0-9_]*$", comparison_name) is None:
                parameters[3].setErrorMessage("The comparison name must start with a letter and contain only letters, numbers, and underscores.")

        if parameters[6].altered:
            comparison_name = parameters[6].valueAsText
            comparison_name = comparison_name.strip()
            if re.match("^[A-Za-z][A-Za-z0-9_]*$", comparison_name) is None:
                parameters[3].setErrorMessage("The comparison name must start with a letter and contain only letters, numbers, and underscores.")


        return
    

    def execute(self, parameters, messages):
        """The source code of the tool."""

        delineation = parameters[0].valueAsText
        discretization = parameters[1].valueAsText
        compare_method = parameters[2].valueAsText
        base_simulation = parameters[3].value
        target_simulation = parameters[4].value
        compare_name = parameters[6].valueAsText
        workspace = parameters[7].valueAsText
       
        compare_method = compare_method[:3]
        simulation_path = os.path.join(os.path.split(workspace)[0], "modeling_files", discretization, "simulations")
        arcpy.AddMessage("Comparing simulation results")
        agwa.process_compare(simulation_path, compare_method, base_simulation, target_simulation, compare_name, workspace)

        arcpy.AddMessage("Joining the comparison table to feature class for display")
        agwa.process_join(discretization, compare_name, workspace)

        return


    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return
