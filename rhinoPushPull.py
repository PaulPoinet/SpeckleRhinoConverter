########################################################## USINGS

import clr
clr.AddReferenceToFileAndPath('C:\\Users\\Paul.Poinet\\AppData\\Roaming\\Grasshopper\\Libraries\\SpeckleSendReceive\\SpeckleCore.dll')
clr.AddReferenceToFileAndPath('C:\\Users\\Paul.Poinet\\AppData\\Roaming\\Grasshopper\\Libraries\\SpeckleSendReceive\\SpeckleRhinoConverter.dll')
import SpeckleCore as sc
import SpeckleRhinoConverter as src
import Rhino
import Rhino.Geometry as rg
import System
import json
import scriptcontext

########################################################## CLIENT

# Set client and Url
c = sc.BaseSpeckleApiClient()
c.BaseUrl = "http://localhost:8080/api"

# Set Login and AuthToken
login = sc.PayloadAccountLogin()
login.Email = "yourEmail@gmail.com"
login.Password = "yourPassword"
responseLogin = c.UserLogin(login)
c.AuthToken = responseLogin.ApiToken

########################################################## CONVERTER

converter = src.RhinoConverter()

########################################################## TABLES

layers = Rhino.RhinoDoc.ActiveDoc.Layers
groups = Rhino.RhinoDoc.ActiveDoc.Groups

settings = Rhino.DocObjects.ObjectEnumeratorSettings()
settings.VisibleFilter = False
settings.IncludeLights = True
settings.IncludeGrips = True
settings.NormalObjects = True
settings.LockedObjects = True
settings.HiddenObjects = True
settings.ActiveObjects = True
settings.SelectedObjectsFilter = True
docObjects = scriptcontext.doc.Objects.GetObjectList(settings)

########################################################## PUSH DATA

def Push():
    
    with open("mongoId.txt","w") as myFile:
        for obj in docObjects:
            
            if obj.IsSelected(False) > 0: # Select the objects that you want to push to the DB and hit run!
                
                #####
                objGeo = obj.Geometry
                objUD = objGeo.UserDictionary
                #print obj.Attributes.GetUserStrings().AllKeys #Need to implement userstrings in the future...
                #####

                # Clear UserDictionary but keep specified properties
                # Not sure if it's useful but was convenient for prototyping
                for k in objUD.Keys:
                    if k == "Name":
                        pass
                    else:
                        objUD.Remove(k)
                    
                    
                # Attach Name
                objUD.Set("Name", obj.Name)
                
                # Attach GroupList
                groupList = list(obj.GetGroupList())
                groupListJson = json.dumps(groupList)
                objUD.Set("GroupList", groupListJson)
                
                # Attach a SpeckleLayer containing both Name and Color attributes
                objLayer = layers.Item[obj.Attributes.LayerIndex]
                
                SpeckleLayerColor = sc.Color()
                SpeckleLayerColor.Hex = '#%02x%02x%02x' % (int(objLayer.Color.R), int(objLayer.Color.G), int(objLayer.Color.B))
                SpeckleLayerProperties = sc.SpeckleLayerProperties()
                SpeckleLayerProperties.Color = SpeckleLayerColor
                
                SpeckleLayer = sc.SpeckleLayer()
                SpeckleLayer.Name = objLayer.FullPath
                SpeckleLayer.Properties = SpeckleLayerProperties
                
                objUD.Set("SpeckleLayer", SpeckleLayer.ToJson())
                
                # Attach ObjectColorSource/ObjectColor
                objColorSource = int(obj.Attributes.ColorSource)
                objUD.Set("ObjectColorSource", objColorSource)
                
                if objColorSource == 0: # ColorFromLayer
                    pass
                    
                if objColorSource == 1: # ColorFromObject
                    SpeckleColor = sc.Color()
                    SpeckleColor.Hex = '#%02x%02x%02x' % (int(obj.Attributes.ObjectColor.R), int(obj.Attributes.ObjectColor.G), int(obj.Attributes.ObjectColor.B))
                    objUD.Set("ObjectColor", SpeckleColor.ToJson())
                
                # Convert object to Speckle, attach GUID and push to DB
                SpeckleObject = converter.ToSpeckle(objGeo)
                SpeckleObject.ApplicationId = str(obj.Id)
                payloadObj = sc.PayloadCreateObject()
                payloadObj.Object = SpeckleObject
                mongoObj = c.ObjectCreate(payloadObj)
                
                # Write all the pushed mongoIDs in a text file so we can retrieve them later (in pull)
                myFile.write(mongoObj.ObjectId+'\n')
                scriptcontext.doc.Objects.Delete(obj, False)
                
            else:
                pass
                
        myFile.close() 

def Pull():
    with open("mongoId.txt","r") as myFile:
        for line in myFile: # read all stored MongoIDs
            line = line.rstrip('\n')
            
            # Retrieve rhino object and dictionary
            speckleObj = c.ObjectGet(line).SpeckleObject
            rhinoObject = converter.ToNative(speckleObj)
            rhUD = rhinoObject.UserDictionary
            
            # Retrieve Name
            Name = rhUD["Name"]
            
            # Retrieve GroupList
            GroupList = rhUD["GroupList"]
            GroupList = json.loads(GroupList)
            
            # Retrieve Layer
            SpeckleLayer = rhUD["SpeckleLayer"]
            SpeckleLayer = json.loads(SpeckleLayer)
            LayerIndex = layers.FindByFullPath(SpeckleLayer["name"], True)
            
            # Retrieve ObjectColorSource
            ObjectColorSource = int(rhUD["ObjectColorSource"])
            
            if LayerIndex >= 0: # Layer exists in active doc
                layer = layers[LayerIndex]
                #layer.IsVisible = True
                #layer.CommitChanges()

                rhinoObjectAtt = Rhino.DocObjects.ObjectAttributes()
                rhinoObjectAtt.LayerIndex = LayerIndex
                rhinoObjectAtt.Visible = True # Makes sure the object is visible (useful for prototyping)
                rhinoObjectAtt.Name = Name
                
                if ObjectColorSource == 1: # ColorFromObject
                    ObjectColor = rhUD["ObjectColor"]
                    ObjectColor = json.loads(ObjectColor)
                    ObjectColor_hex = ObjectColor['hex']
                    ObjectColor_rgb = list(int(ObjectColor_hex[1:][i:i+2], 16) for i in (0, 2 ,4))
                    ObjectColor = System.Drawing.Color.FromArgb(ObjectColor_rgb[0], ObjectColor_rgb[1], ObjectColor_rgb[2])
                    rhinoObjectAtt.ObjectColor = ObjectColor
                    rhinoObjectAtt.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
                    
                    
                else: # in this case the color will depends on the layer's color. Have to handle materials as well... todo
                    pass
                
                # iterates through the retrieved groups and add the retrieved object to them.
                for g in GroupList:
                    rhinoObjectAtt.AddToGroup(g)
                    groups.Show(g)
                
                if type(rhinoObject) is rg.TextEntity:
                    # it's weird. "ObjectTable.Add" does not work properly for TextEntity. It does not keep the attributes.
                    # I had to make an exception for that...
                    objGUID = scriptcontext.doc.Objects.AddText(rhinoObject, rhinoObjectAtt)
                else: 
                    objGUID = scriptcontext.doc.Objects.Add(rhinoObject, rhinoObjectAtt)
                    
            else: # The retrieved layer do not exist in active dot
                # DO SOME STUFF!
                pass

Push()
Pull()

