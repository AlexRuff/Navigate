
# ==================================================
# DismountedCCM.py
# --------------------------------------------------
# Built on ArcGIS 10.2 tried to import to Python3
# --------------------------------------------------
#
# Generates a dismounted Cross Country Mobility raster product based on slope/speed characteristics,
# soil, and vegetation.
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
#Spatial reference
GCS_WGS_1984 = arcpy.SpatialReference("WGS 1984")
webMercator = arcpy.SpatialReference("WGS 1984 Web Mercator (Auxiliary Sphere)")
#list of factors. There are four possible factors that can be used. Soils, Surface roughness, vegitation, and slope.
ccmFactorList = []

# ARGUMENTS ========================================
inputAOI =arcpy.GetParameterAsText(0)
# This is the area of interest polygon for Madera Canyon. Can be hard coded as a parameter or have the user define area.
##r"T:\gist_601\aruff\CrossCountryMobility\MaderaEnvironment.gdb\MADERA_AOI"
#arcpy.GetParameterAsText(0) # area of interest polygon

#Whether it is day or night. Visibility will change the movement speed. My default is day
inputVisibility = arcpy.GetParameterAsText(1)
##"Day"

#This is a reference table displaying the max movement speed for a soldier during the day and during the night. Also, max slope for both visibility types.

inputFootMarchParameterTable = arcpy.GetParameterAsText(2)
##r"T:\gist_601\aruff\CrossCountryMobility\SupportingData.gdb\maotFootMarchParameters"

#DEM for the area is used here

inputElevation = arcpy.GetParameterAsText(3)
##r"T:\gist_601\aruff\CrossCountryMobility\maderadem"

#Output of the tool

outputCCM = arcpy.GetParameterAsText(4)
#r"Z:\CrossCountryMobility\MaderaCanyonData\test"

#Land cover vectors showing the type of vegitaion in Madera. Created from an unsupervised classification. The vegitation must be coded with an f_code that matches the reference table
inputVegetation = arcpy.GetParameterAsText(5)
##r"T:\gist_601\aruff\CrossCountryMobility\MaderaEnvironment.gdb\MaderaCanyon\LandCover"
inputVegetationTable = arcpy.GetParameterAsText(6)
## r"T:\gist_601\aruff\CrossCountryMobility\SupportingData.gdb\maotLandCover"
#Vegitation coverage. Max indicates dense vegitation.
min_max = arcpy.GetParameterAsText(7) # "MAX" or "MIN", where "MAX" is default
##MIN

#Soils table
inputSoils = arcpy.GetParameterAsText(8)
##r"T:\gist_601\aruff\CrossCountryMobility\MaderaEnvironment.gdb\MaderaCanyon\Soils"
inputSoilsTable = arcpy.GetParameterAsText(9)
##r"T:\gist_601\aruff\CrossCountryMobility\SupportingData.gdb\maotSoils"
wet_dry = arcpy.GetParameterAsText(10) # "DRY" or "WET", where "DRY" is default
##DRY

#Surface roughness. I calculated this raster from the DEM using the following formula (MeanDEM - MinDEM)/MaxDEM - MinDEM). MinDEM, MeanDEM and MaxDEM created with focal statistics
inputSurfaceRoughness = arcpy.GetParameterAsText(11)
##r"T:\gist_601\aruff\CrossCountryMobility\MaderaEnvironment.gdb\MaderaCanyon\Surface_Rough"

#Reference table
inputRoughnessTable = arcpy.GetParameterAsText(12)
##"T:\gist_601\aruff\CrossCountryMobility\SupportingData.gdb\maotSurfaceRoughness"
#
#Soldiers weight. Default is 185lbs.
inputWeight = arcpy.GetParameterAsText(13)
##"185"
# ==================================================
#Modeling
#Extents and masks for the area of interest.
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

    elevationRaster = arcpy.Raster(inputElevation)
    elevationDescription = arcpy.Describe(inputElevation)
    elevationCellSize = elevationDescription.children[0].meanCellHeight
    env.cellSize=elevationCellSize

    if debug == True:
        arcpy.AddMessage("inputAOI: " + str(inputAOI))
        arcpy.AddMessage("Extent: " + str(env.extent))
        arcpy.AddMessage("Visibility: " + inputVisibility)
        arcpy.AddMessage("Foot march table: " + inputFootMarchParameterTable)
        arcpy.AddMessage("Input Weight: " + inputWeight)
    intersectionList = []

    # Retrieve speed from table based on visibility: day or night
    arcpy.AddMessage("Retrieving foot march info based on visibility...")
    expression = arcpy.AddFieldDelimiters(inputFootMarchParameterTable, "visibility") + " = '" + inputVisibility + "'"

    #There should only be one row
    with arcpy.da.SearchCursor(inputFootMarchParameterTable,["maxmph", "onslope"], where_clause=expression) as marchCursor:
        for row in marchCursor:
            speed = float(row[0])
            maxSlopePercent = float(row[1])

    arcpy.AddMessage("Speed: " + str(speed))
    arcpy.AddMessage("Max slope: " + str(maxSlopePercent))


    arcpy.AddMessage("Generating slope...")
    slopeClip = os.path.join(scratch,"slopeClip")
    outSlope = sa.Slope(inputElevation, "PERCENT_RISE")
    outSlope.save(slopeClip)
    deleteme.append(slopeClip)


    # Set all Slope values greater than the foot march max slope percent to the max foot march slope value
    arcpy.AddMessage("Reclassifying Slope ...")
    reclassSlope = os.path.join(scratch,"reclassSlope")
    if debug == True:
        arcpy.AddMessage("reclassSlope: " + str(reclassSlope))
#conditional statment. If the slope in the DEM is less than or equal to the Max slope percent in the movement table return values.
    if debug == True:
        arcpy.AddMessage(str(time.strftime("Performing Con on slope: %m/%d/%Y  %H:%M:%S", time.localtime())))
    outCon = sa.Con(sa.Raster(slopeClip) >= float(maxSlopePercent),float(maxSlopePercent),sa.Raster(slopeClip))
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
    # f1: foot march parameters
    f1 = os.path.join(env.scratchFolder,"f1.tif")
    if debug == True:
        arcpy.AddMessage(str(time.strftime("F1: %m/%d/%Y  %H:%M:%S", time.localtime())))
    slopeAsRaster = sa.Raster(reclassSlope)

    #Original formula for vehicles
    #outF1 = (float(minVehicleOnRoadSlope) - slopeAsRaster) / (float(minVehicleKPH) / float(maxVehicleWeight))

    # For humans:
    # 1 short ton = 2000 lbs
    # The original formula, based on vehicle movement speed, takes in short tons; therefore, (human weight/2000)
    weight = float(inputWeight)
    #speed from visibility table devided by weight
    speedOverWt = (float(speed) / float(weight/2000.0))
    outF1 = (float(maxSlopePercent) - slopeAsRaster) / speedOverWt # hard code human weight to be 150 lbs
    outF1.save(f1)
    ccmFactorList.append(f1)
    deleteme.append(f1)

    ##########################################################
    # F2: surface change
    ##########################################################
    #Curvature of surface or slope of the slope.  Curvature calculates the curvature of a raster surface, optionally including profile and plan curvature.
    arcpy.AddMessage("Surface Curvature ...")
    f2 = os.path.join(env.scratchFolder,"f2.tif")
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

    # F2 Final values for CCM List
    maxRasStat = float(str(arcpy.GetRasterProperties_management(focalStats,"MAXIMUM")))
    fsRasStat = sa.Raster(focalStats)
    if debug == True:
        arcpy.AddMessage("maxRasStat: " + str(maxRasStat) + " - " + str(type(maxRasStat)))
        arcpy.AddMessage("fsRasStat: " + str(fsRasStat) + " - " + str(type(fsRasStat)))
    f2Calc = (maxRasStat - fsRasStat) / maxRasStat # (max - cell/max)
    f2Calc.save(f2)
    deleteme.append(f2)
    ccmFactorList.append(f2)

    ##########################################################
    # F3: vegetation
    ##########################################################
    #Vegetation factor (f3) derived from unsupervised classification of NAIP imagery for Madera

    if inputVegetation != type(None) and arcpy.Exists(inputVegetation) == True:
        f3t = os.path.join(scratch,"f3t")
        f3 = os.path.join(scratch,"f3")
        arcpy.AddMessage("Clipping vegetation to fishnet and joining parameter table...")
        vegetation = os.path.join("in_memory","vegetation")
        if debug == True: arcpy.AddMessage(str(time.strftime("Clip Vegetation: %m/%d/%Y  %H:%M:%S", time.localtime())))
        #Clip the vegitation layer to the AOI
        arcpy.Clip_analysis(inputVegetation,inputAOI,vegetation)
        deleteme.append(vegetation)
        arcpy.JoinField_management(vegetation,"f_code",inputVegetationTable,"f_code")
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
        ccmFactorList.append(f3)

    ##########################################################
    # F4: soils
    ##########################################################
    #Soils factor F4. Soils layer from USDA soil map.
    if inputSoils != type(None) and  arcpy.Exists(inputSoils) == True:
        f4t = os.path.join(scratch,"f4t")
        f4 = os.path.join(scratch,"f4")
        arcpy.AddMessage("Clipping soils to fishnet and joining parameter table...")
        #clip soils layer to AOI
        clipSoils = os.path.join("in_memory","clipSoils")
        if debug == True: arcpy.AddMessage(str(time.strftime("Clip Soils: %m/%d/%Y  %H:%M:%S", time.localtime())))
        arcpy.Clip_analysis(inputSoils,inputAOI,clipSoils)
        deleteme.append(clipSoils)

        #Join the soils layer to the soils reference table based on soilcode field.
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
        #Add to ccmFactorList
        ccmFactorList.append(f4)

    ##########################################################
    # F4: surface roughness
    ##########################################################
    #Surface roughness factor F4. Derived from DEM in vector format
    if inputSurfaceRoughness != type(None) and  arcpy.Exists(inputSurfaceRoughness) == True:
        f5t = os.path.join(scratch,"f5t")
        f5 = os.path.join(scratch,"f5")
        arcpy.AddMessage("Clipping roughness to fishnet and joining parameter table...")
        clipRoughness = os.path.join("in_memory","clipRoughness")
        if debug == True: arcpy.AddMessage(str(time.strftime("Clip Roughness: %m/%d/%Y  %H:%M:%S", time.localtime())))
        arcpy.Clip_analysis(inputSurfaceRoughness,inputAOI,clipRoughness)

        # Join roughness table to the surface roughness layer based on roughnesscode.
        arcpy.JoinField_management(clipRoughness,"roughnesscode",inputRoughnessTable,"roughnesscode")
        intersectionList.append(clipRoughness)

        # Convert surface roughness to raster
        arcpy.PolygonToRaster_conversion(clipRoughness,"f5",f5t)
        deleteme.append(f5t)
        outF5T = sa.Con(sa.IsNull(f5t),constNoEffect,f5t)
        outF5T.save(f5)
        deleteme.append(f5)
        #add to ccmFactor list
        ccmFactorList.append(f5)

    # Map Algebra to calc final CCM
    if debug == True: arcpy.AddMessage("BEFORE: " + str(ccmFactorList) + str(time.strftime(" %m/%d/%Y  %H:%M:%S", time.localtime())))
    tempCCM = os.path.join(env.scratchFolder,"tempCCM.tif")
    targetCCM = ""
    #Map algebra based on number of factors in ccmFactorlist.
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
        raise WrongFactors(ccmFactorList)
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

except "WrongFactors" as ccmlist:
    msg = "Wrong Number of Factors given: " + str(ccmlist)
    arcpy.AddError(msg)
    print(msg)

except arcpy.ExecuteError:
    if debug == True: arcpy.AddMessage("CRASH: " + str(time.strftime("%m/%d/%Y  %H:%M:%S", time.localtime())))
        # Get the traceback object
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]
    arcpy.AddError("Traceback: " + tbinfo)
    # Get the tool error messages
    msgs = arcpy.GetMessages()
    arcpy.AddError(msgs)
    print(msgs)

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
    print(pymsg + "\n")
    print(msgs)

