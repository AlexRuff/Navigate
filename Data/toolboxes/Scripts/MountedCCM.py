
# ==================================================
# MountedCCM.py
# --------------------------------------------------
# Built on ArcGIS 10.2
# --------------------------------------------------
#
# Generates a mounted Cross Country Mobility raster product based on the lowest common denominator
# for vehicle characteristics in a convoy, slope/speed characteristics, soil, and vegetation.
#
# Data is presumed to be in the WGS 1984 Auxiliary Sphere spatial reference (GCS_WGS_1984)
#
# Spatial Analyst is required.
#
# ==================================================


# IMPORTS ==========================================
import os, sys, math, traceback, types
import arcpy
from arcpy import da
from arcpy import env
from arcpy import sa


# LOCALS ===========================================
# Check out the ArcGIS Spatial Analyst extension license
arcpy.CheckOutExtension("Spatial")
deleteme = []
debug = True
GCS_WGS_1984 = arcpy.SpatialReference("WGS 1984")
webMercator = arcpy.SpatialReference("WGS 1984 Web Mercator (Auxiliary Sphere)")
ccmFactorList = []

# ARGUMENTS ========================================
inputAOI = arcpy.GetParameterAsText(0)
inputVehicleParameterTable = arcpy.GetParameterAsText(1)

# The vehicle types for which the CCM should be generated.  There will be at least one, possibly more.
inputVehicleTypes = arcpy.GetParameterAsText(2)

inputElevation = arcpy.GetParameterAsText(3)

outputCCM = arcpy.GetParameterAsText(4)

inputVegetation = arcpy.GetParameterAsText(5)
inputVegetationConversionTable = arcpy.GetParameterAsText(6)
min_max = arcpy.GetParameterAsText(7) # "MAX" or "MIN", where "MAX" is default

inputSoils = arcpy.GetParameterAsText(8)
inputSoilsTable = arcpy.GetParameterAsText(9)
wet_dry = arcpy.GetParameterAsText(10) # "DRY" or "WET", #where "DRY" is default

inputSurfaceRoughness = arcpy.GetParameterAsText(11)
inputRoughnessTable = arcpy.GetParameterAsText(12)

# ==================================================

env.extent = inputAOI
env.snapRaster = inputElevation
env.mask = inputAOI

try:

    if debug == True:
        arcpy.AddMessage("START: " + str(time.strftime("%m/%d/%Y  %H:%M:%S", time.localtime())))
    scratch = env.scratchGDB
    if debug == True: arcpy.AddMessage("scratch: " + str(scratch))
    env.overwriteOutput = True
    env.resample = "NEAREST"
    env.compression = "LZ77"
    env.rasterStatistics = 'STATISTICS'

    ######################################################
    # How many vehicles have been specified?
    ######################################################
    splitVehicleTypes =  inputVehicleTypes.split(";")
    numVehicleTypes = len(splitVehicleTypes)

    elevationRaster = arcpy.Raster(inputElevation)
    elevationDescription = arcpy.Describe(inputElevation)
    elevationCellSize = elevationDescription.children[0].meanCellHeight
    env.cellSize=elevationCellSize

    if debug == True:
        arcpy.AddMessage("inputAOI: " + str(inputAOI))
        arcpy.AddMessage("Extent: " + str(env.extent))
        arcpy.AddMessage("Vehicle Types: " + str(inputVehicleTypes))
        arcpy.AddMessage("Number of Vehicle Types: " + str(numVehicleTypes))
        arcpy.AddMessage("Cell Size: " + str(env.cellSize))
    intersectionList = []

    ######################################################
    # Determine the set of vehicles that are in the Convoy, and from them, find the range of tolerances
    # for vehicle weight, max
    ######################################################

    # First, create a table view consiting of only the specified vehicles
    VEHICLE_PARAMETER_VIEW = os.path.join(scratch,"vehicleParameter_tview")
    vehicleTypeWhereClause = ""
    if numVehicleTypes == 1:
        strVehicleTypes = str(inputVehicleTypes)
        if strVehicleTypes.startswith("'") == False:
            strVehicleTypes = "'" + strVehicleTypes
        if strVehicleTypes.endswith("'") == False:
            strVehicleTypes = strVehicleTypes +  "'"
        vehicleTypeWhereClause = "\"name\" = " + inputVehicleTypes
    elif numVehicleTypes > 1:
        vehicleTypeIn = ""
        n = 1
        for oVehicleType in splitVehicleTypes:
            vehicleType = str(oVehicleType)
            if vehicleType.startswith("'") == False:
                vehicleType = "'" + vehicleType
            if vehicleType.endswith("'") == False:
                vehicleType = vehicleType +  "'"
            vehicleTypeIn = vehicleTypeIn + vehicleType
            if n < numVehicleTypes:
                vehicleTypeIn = vehicleTypeIn + ", "
            n = n + 1
        vehicleTypeWhereClause = "\"name\" IN (" + vehicleTypeIn + ")"

    if debug == True:
        arcpy.AddMessage("vehicleTypeWhereClause: " + vehicleTypeWhereClause)
    arcpy.AddMessage("Selecting vehicles in convoy...")

    arcpy.MakeTableView_management(inputVehicleParameterTable, VEHICLE_PARAMETER_VIEW, vehicleTypeWhereClause)

    # Next, get the minimum speeds on-, and off-road slopes and the min and max weights from the view.  The minimum values in the table are the maximum supported tolerances
    # for all vehicles in the convoy.  Note, weight is measured in short tons.
    VEHICLE_STATISTICS = os.path.join(scratch,"vehicle_statistics")
    deleteme.append(VEHICLE_STATISTICS)
    arcpy.AddMessage("Generating vehicle statistics...")
    arcpy.Statistics_analysis(VEHICLE_PARAMETER_VIEW, VEHICLE_STATISTICS, [["weight","MIN"],["weight", "MAX"],["maxkph", "MIN"],["onslope", "MIN"],["offslope","MIN"]])

    # VEHICLE_STATISTICS will contain one row, with that row specifying the aforementioned tolerances.
    arcpy.AddMessage("Retrieving vehicle statistics...")
    vehicleCursor = arcpy.da.SearchCursor(VEHICLE_STATISTICS,["MIN_weight","MAX_weight","MIN_maxkph","MIN_onslope","MIN_offslope"])
    vehicleRow = vehicleCursor.next()
    while vehicleCursor:
        minVehicleWeight = float(vehicleRow[0])
        maxVehicleWeight = float(vehicleRow[1])
        minVehicleKPH = float(vehicleRow[2])
        minVehicleOnRoadSlope = float(vehicleRow[3])
        minVehicleOffRoadSlope = float(vehicleRow[4])
        break
    del vehicleCursor

    if debug == True:
        arcpy.AddMessage("minVehicleWeight: " + str(minVehicleWeight))
        arcpy.AddMessage("maxVehicleWeight: " + str(maxVehicleWeight))
        arcpy.AddMessage("minVehicleKPH: " + str(minVehicleKPH))
        arcpy.AddMessage("minVehicleOnRoadSlope: " + str(minVehicleOnRoadSlope))
        arcpy.AddMessage("minVehicleOffRoadSlope: " + str(minVehicleOffRoadSlope))
        arcpy.AddMessage("Initial Cell Size (Environment): " + str(env.cellSize))

    arcpy.AddMessage("Generating slope...")
    slopeClip = os.path.join(scratch,"slopeClip")
    outSlope = sa.Slope(inputElevation, "PERCENT_RISE", 1)
    outSlope.save(slopeClip)
    deleteme.append(slopeClip)


    # Set all Slope values greater than the vehicle's off road max to that value
    arcpy.AddMessage("Reclassifying Slope ...")
    reclassSlope = os.path.join(scratch,"reclassSlope")
    if debug == True:
        arcpy.AddMessage("reclassSlope: " + str(reclassSlope))
        arcpy.AddMessage("minVehicleOnRoadSlope: " + str(minVehicleOnRoadSlope))
    #float(minVehicleOnRoadSlope)
    if debug == True:
        arcpy.AddMessage(str(time.strftime("Con: %m/%d/%Y  %H:%M:%S", time.localtime())))
    outCon = sa.Con(sa.Raster(slopeClip) >= float(minVehicleOnRoadSlope),float(minVehicleOnRoadSlope),sa.Raster(slopeClip))
    # FAILS HERE:
    outCon.save(reclassSlope)
    deleteme.append(reclassSlope)

    # make constant raster
    constNoEffect = os.path.join(scratch,"constNoEffect")
    outConstNoEffect = sa.CreateConstantRaster(1.0,"FLOAT",inputElevation,arcpy.Describe(inputAOI).Extent)
    outConstNoEffect.save(constNoEffect)
    deleteme.append(constNoEffect)

    ##########################################################
    # F1: Calculate Slope/Speed Characteristics.
    ##########################################################
    # f1: vehicle parameters
    f1 = os.path.join(env.scratchFolder,"f1.tif")
    # f1 = (vehicle max off-road slope %) - (surface slope %) / (vehicle max on-road slope %) / (vehicle max KPH)
    if debug == True:
        arcpy.AddMessage(str(time.strftime("F1: %m/%d/%Y  %H:%M:%S", time.localtime())))
        arcpy.AddMessage("slopeClip: " + str(slopeClip))
    slopeAsRaster = sa.Raster(reclassSlope)
    outF1 = (float(minVehicleOnRoadSlope) - slopeAsRaster) / (float(minVehicleKPH) / float(maxVehicleWeight))
    outF1.save(f1)
    ccmFactorList.append(f1)
    deleteme.append(f1)


    # f2: surface change
    arcpy.AddMessage("Surface Curvature ...")
    f2 = os.path.join(env.scratchFolder,"f2.tif")
    #f2 = os.path.join(scratch,"f2.tif")
    if debug == True: arcpy.AddMessage(str(time.strftime("Curvature: %m/%d/%Y  %H:%M:%S", time.localtime())))
    # CURVATURE
    curvature = os.path.join(scratch,"curvature")
    curveSA = sa.Curvature(inputElevation)
    curveSA.save(curvature)
    deleteme.append(curvature)
    if debug == True: arcpy.AddMessage(str(time.strftime("Focal Stats: %m/%d/%Y  %H:%M:%S", time.localtime())))
    # FOCALSTATISTICS (RANGE)
    focalStats = os.path.join(scratch,"focalStats")
    window = sa.NbrCircle(3,"CELL")
    fstatsSA = sa.FocalStatistics(curvature,window,"RANGE")
    fstatsSA.save(focalStats)
    deleteme.append(focalStats)
    # F2
    maxRasStat = float(str(arcpy.GetRasterProperties_management(focalStats,"MAXIMUM")))
    fsRasStat = sa.Raster(focalStats)
    if debug == True:
        arcpy.AddMessage("maxRasStat: " + str(maxRasStat) + " - " + str(type(maxRasStat)))
        arcpy.AddMessage("fsRasStat: " + str(fsRasStat) + " - " + str(type(fsRasStat)))
    f2Calc = (maxRasStat - fsRasStat) / maxRasStat # (max - cell/max)
    f2Calc.save(f2)
    deleteme.append(f2)
    ccmFactorList.append(f2)

    #TODO: Need more thorough and complete checks of inputs
    if inputVegetation != types.NoneType and arcpy.Exists(inputVegetation) == True:
        # f3: vegetation
        f3t = os.path.join(scratch,"f3t")
        f3 = os.path.join(scratch,"f3")
        arcpy.AddMessage("Clipping vegetation to fishnet and joining parameter table...")
        vegetation = os.path.join("in_memory","vegetation")
        if debug == True: arcpy.AddMessage(str(time.strftime("Clip Vegetation: %m/%d/%Y  %H:%M:%S", time.localtime())))
        arcpy.Clip_analysis(inputVegetation,inputAOI,vegetation)
        deleteme.append(vegetation)
        arcpy.JoinField_management(vegetation,"f_code",inputVegetationConversionTable,"f_code")
        # Convert vegetation to Raster using MIN or MAX field
        if min_max == "MAX":
            arcpy.PolygonToRaster_conversion(vegetation,"f3max",f3t)
        else:
            arcpy.PolygonToRaster_conversion(vegetation,"f3min",f3t)
        # if F3T is null, make it 1.0 (from constNoEffect), otherwise keep F3T value
        outF3T = sa.Con(sa.IsNull(f3t),constNoEffect,f3t)
        outF3T.save(f3)
        deleteme.append(f3t)
        deleteme.append(f3)
        #TODO: what about areas in the AOI but outside VEG? No effect (value = 1.0)?
        ccmFactorList.append(f3)

    if inputSoils != types.NoneType and  arcpy.Exists(inputSoils) == True:
        # f4: soils
        f4t = os.path.join(scratch,"f4t")
        f4 = os.path.join(scratch,"f4")
        arcpy.AddMessage("Clipping soils to fishnet and joining parameter table...")
        clipSoils = os.path.join("in_memory","clipSoils")
        if debug == True: arcpy.AddMessage(str(time.strftime("Clip Soils: %m/%d/%Y  %H:%M:%S", time.localtime())))
        arcpy.Clip_analysis(inputSoils,inputAOI,clipSoils)
        deleteme.append(clipSoils)
        arcpy.JoinField_management(clipSoils,"soilcode",inputSoilsTable,"soilcode")
        # Convert soils to Raster using WET or DRY field
        if wet_dry == "DRY":
            arcpy.PolygonToRaster_conversion(clipSoils,"f4dry",f4t)
        else:
            arcpy.PolygonToRaster_conversion(clipSoils,"f4wet",f4t)
        deleteme.append(f4t)
        outF4T = sa.Con(sa.IsNull(f4t),constNoEffect,f4t)
        outF4T.save(f4)
        deleteme.append(f4)
        ccmFactorList.append(f4)

    if inputSurfaceRoughness != types.NoneType and  arcpy.Exists(inputSurfaceRoughness) == True:
        # f5: surface roughness
        f5t = os.path.join(scratch,"f5t")
        f5 = os.path.join(scratch,"f5")
        arcpy.AddMessage("Clipping roughness to fishnet and joining parameter table...")
        clipRoughness = os.path.join("in_memory","clipRoughness")
        if debug == True: arcpy.AddMessage(str(time.strftime("Clip Roughness: %m/%d/%Y  %H:%M:%S", time.localtime())))
        arcpy.Clip_analysis(inputSurfaceRoughness,inputAOI,clipRoughness)
        # Join roughness table
        arcpy.JoinField_management(clipRoughness,"roughnesscode",inputRoughnessTable,"roughnesscode")
        intersectionList.append(clipRoughness)
        # Convert surface roughness to raster
        arcpy.PolygonToRaster_conversion(clipRoughness,"f5",f5t)
        deleteme.append(f5t)
        outF5T = sa.Con(sa.IsNull(f5t),constNoEffect,f5t)
        outF5T.save(f5)
        deleteme.append(f5)
        ccmFactorList.append(f5)

    # Map Algebra to calc final CCM
    if debug == True: arcpy.AddMessage("BEFORE: " + str(ccmFactorList) + str(time.strftime(" %m/%d/%Y  %H:%M:%S", time.localtime())))
    tempCCM = os.path.join(env.scratchFolder,"tempCCM.tif")
    targetCCM = ""
    if len(ccmFactorList) == 2:
        if debug == True: arcpy.AddMessage(str(time.strftime("Two factors " + str(ccmFactorList) + " : %m/%d/%Y  %H:%M:%S", time.localtime())))
        targetCCM = sa.Raster(ccmFactorList[0]) * sa.Raster(ccmFactorList[1])
    elif len(ccmFactorList) == 3:
        if debug == True: arcpy.AddMessage(str(time.strftime("Three factors " + str(ccmFactorList) + " : %m/%d/%Y  %H:%M:%S", time.localtime())))
        targetCCM = sa.Raster(ccmFactorList[0]) * sa.Raster(ccmFactorList[1]) * sa.Raster(ccmFactorList[2])
    elif len(ccmFactorList) == 4:
        if debug == True: arcpy.AddMessage(str(time.strftime("Four factors " + str(ccmFactorList) + " : %m/%d/%Y  %H:%M:%S", time.localtime())))
        targetCCM = sa.Raster(ccmFactorList[0]) * sa.Raster(ccmFactorList[1]) * sa.Raster(ccmFactorList[2]) * sa.Raster(ccmFactorList[3])
    elif len(ccmFactorList) == 5:
        if debug == True: arcpy.AddMessage(str(time.strftime("Five factors " + str(ccmFactorList) + " : %m/%d/%Y  %H:%M:%S", time.localtime())))
        targetCCM = sa.Raster(ccmFactorList[0]) * sa.Raster(ccmFactorList[1]) * sa.Raster(ccmFactorList[2]) * sa.Raster(ccmFactorList[3]) * sa.Raster(ccmFactorList[4])
    else:
        if debug == True: arcpy.AddMessage("ERROR!!!!!: " + str(ccmFactorList) + str(time.strftime(" %m/%d/%Y  %H:%M:%S", time.localtime())))
        raise WrongFactors, ccmFactorList
    deleteme.append(tempCCM)
    targetCCM.save(tempCCM)

    #save the output
    arcpy.CopyRaster_management(tempCCM,outputCCM)


    # set the output
    arcpy.SetParameter(5,outputCCM)
    if debug == True: arcpy.AddMessage("DONE: " + str(time.strftime("%m/%d/%Y  %H:%M:%S", time.localtime())))

    # cleanup intermediate datasets
    if debug == True: arcpy.AddMessage("Removing intermediate datasets...")
    for i in deleteme:
        if debug == True: arcpy.AddMessage("Removing: " + str(i))
        if arcpy.Exists(i):
            arcpy.Delete_management(i)
            pass
    if debug == True: arcpy.AddMessage("Done")

except "WrongFactors", ccmlist:
    msg = "Wrong Number of Factors given: " + str(ccmlist)
    arcpy.AddError(msg)
    print msg

except arcpy.ExecuteError:
    if debug == True: arcpy.AddMessage("CRASH: " + str(time.strftime("%m/%d/%Y  %H:%M:%S", time.localtime())))
        # Get the traceback object
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]
    arcpy.AddError("Traceback: " + tbinfo)
    # Get the tool error messages
    msgs = arcpy.GetMessages()
    arcpy.AddError(msgs)
    print msgs

except:
    if debug == True: arcpy.AddMessage("CRASH: " + str(time.strftime("%m/%d/%Y  %H:%M:%S", time.localtime())))
    # Get the traceback object
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]

    # Concatenate information together concerning the error into a message string
    pymsg = "PYTHON ERRORS:\nTraceback info:\n" + tbinfo + "\nError Info:\n" + str(sys.exc_info()[1])
    msgs = "ArcPy ERRORS:\n" + arcpy.GetMessages() + "\n"

    # Return python error messages for use in script tool or Python Window
    arcpy.AddError(pymsg)
    arcpy.AddError(msgs)

    # Print Python error messages for use in Python / Python Window
    print pymsg + "\n"
    print msgs

