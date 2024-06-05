import arcpy
import arcpy.management
import os


def tweet(msg):
    """Produce a message for both arcpy and python
    : msg - a text message
    """
    m = "\n{}\n".format(msg)
    arcpy.AddMessage(m)
    print(m)
    print(arcpy.GetMessages())


def join_tables(workspace_par, discretization_par, parameterization_name_par, simulation_name_par):
    """
    Join the results table to both the Plane and Channel feature classes and export to new feature classes. 
    """
    tweet("Joining simulation results with discretization features")

    simulation_gdb = r'E:\agwa_pro_prj\from_Shea_pro_tutorial\agwa_pond_demo\pond208\Pond208_fl1000\simulations\demo3251\demo3251_results.gdb'
    arcpy.env.workspace = simulation_gdb
    simulation_results_table = 'results_k2'
    
    # Create feature layers from the feature classes
    plane_layer = f'{discretization_par}_elements_layer'
    channel_layer = f'{discretization_par}_streams_layer'
    arcpy.management.MakeFeatureLayer(os.path.join(workspace_par, f'{discretization_par}_elements'), plane_layer)
    arcpy.management.MakeFeatureLayer(os.path.join(workspace_par, f'{discretization_par}_streams'), channel_layer)

    # Join the simulation results to the feature layers
    arcpy.management.AddJoin(plane_layer, "Element_ID", simulation_results_table, "Element_ID", "KEEP_ALL")
    arcpy.management.AddJoin(channel_layer, "Stream_ID", simulation_results_table, "Element_ID", "KEEP_ALL")

    # Export the joined layers to new feature classes
    arcpy.management.CopyFeatures(plane_layer, f'{discretization_par}_elements_joined')
    arcpy.management.CopyFeatures(channel_layer, f'{discretization_par}_streams_joined')

    tweet("Join operation and export completed")
    
    return  


def view_k2_results(discretization_par, simulation_par, unit_par, output_par, workspace_par):

    # simulation_name = os.path.split(simulation_par)
    # results_gdb_abspath = os.path.join(simulation_par, f"{simulation_name}_results.gdb")      

    # add features to map


    # plot     
    if output_par == "Runoff (mm)":
        column_to_plot = f"results_k2_Outflow_{unit_par}" 
    else:
        column_to_plot = f"results_k2_{unit_par}"

    aprx = arcpy.mp.ArcGISProject('CURRENT')		
    m = aprx.listMaps('Map')[0]		
    lyr = m.listLayers(f"{discretization_par}_elements_joined")[0]		
    sym = lyr.symbology
    sym.updateRenderer('GraduatedColorsRenderer')	
    sym.renderer.colorRamp = aprx.listColorRamps("Blue-Green (9 Classes)")[0]
    sym.renderer.classificationField = column_to_plot
    sym.renderer.breakCount = 9  
    lyr.symbology = sym


    lyr = m.listLayers(f"{discretization_par}_streams_joined")[0]		
    sym = lyr.symbology
    sym.updateRenderer('GraduatedColorsRenderer')		
    sym.renderer.colorRamp = aprx.listColorRamps("Orange-Red (9 Classes)")[0]
    sym.renderer.classificationField = column_to_plot
    sym.renderer.breakCount = 9
    lyr.symbology = sym

    tweet("Visulaization simulation results completed")

