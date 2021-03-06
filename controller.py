
# Salama controller class used to control salama.py.
# Class that contains all the required functionalities to
# parse and use lightning observation data from FMI.
# Ville Ilkka, 2017-

# Use use the C implementation if possible, since it is
# much faster and consumes significantly less memory
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

from datetime import datetime, time, timedelta
import mysql.connector
import time
try:
    import urllib2
except ImportError:
    import urllib.request as urllib2
import sys
import json

# Configuration directory
# default: settings/
CNFDIR  = "settings/"


class salamaclass:


    def __init__(self, verbose):
        self.verbose = verbose


    def debug(self, text):
        if(self.verbose == True):
            print(text)

            
    def formatter(self, data, format, lines):
        # format data
        # default: ascii
        # if lines != -1, remove excess data
        output = []
        if(lines > 0):
            # output only the number of lines amount of data            
            output = data
            # output = data
            data = output[0:int(lines)]
        output = []
        if(format == "array"):
            return data
        if(format == "csv"):
            for row in data:
                row = row.replace(" ", ",")
                output.append(row)
            return output
        elif(format == "json"):
            for row in data:
                line = row.split(" ")
                outputlist = {}
                outputlist.update({"time": line[0]})
                outputlist.update({"lat": line[1]})
                outputlist.update({"lon ": line[2]})
                outputlist.update({"peakcurrent": line[3]})
                outputlist.update({"multiplicity": line[4]})
                outputlist.update({"cloudindicator": line[5]})
                outputlist.update({"ellipsemajor": line[6]})
                output.append(outputlist)
            #return output
            jsondata = json.dumps(output)
            return jsondata
        else:
            return data
                
    
    def check_date(self, starttime, endtime):
        # Check that timestamps are valid and
        # that starttime < endtime 
        try:
            time.strptime(starttime, "%Y-%m-%dT%H:%M:%S")
            time.strptime(endtime, "%Y-%m-%dT%H:%M:%S")
        except ValueError as error:
            print(error)
            return False
        else:
            # convert timestamps to seconds
            start = datetime.strptime(starttime, "%Y-%m-%dT%H:%M:%S")
            end   = datetime.strptime(endtime, "%Y-%m-%dT%H:%M:%S")
            start = time.mktime(start.timetuple())
            end   = time.mktime(end.timetuple())
            if(end - start > 168*60*6):
                self.debug("Time interval is more than 168 hours")
                self.debug("Adjust endtime to starttime + 12 hours")
                start = datetime.strptime(starttime, "%Y-%m-%dT%H:%M:%S")
                end   = start + timedelta(hours=12)
                endtime    = end.strftime('%Y-%m-%dT%H:%M:%S')
                starttime  = start.strftime('%Y-%m-%dT%H:%M:%S')
                self.debug("starttime: " + starttime)
                self.debug("endtime: " + endtime)
                return starttime, endtime
            elif(end - start < 0):
                self.debug("endtime < startime")
                starttime, endtime = self.adjust_date(starttime, endtime)
                self.debug("Starttime is greater than endtime -> adjust startime")
                self.debug("Starttime: "+starttime)
                self.debug("Endtime: "+endtime)
                return starttime,endtime
            else:
                return starttime,endtime

            
    def adjust_date(self, starttime, endtime):
        endtime   = datetime.strptime(endtime, "%Y-%m-%dT%H:%M:%S").strftime('%Y-%m-%dT%H:%M:%S')
        starttime = (datetime.strptime(endtime, "%Y-%m-%dT%H:%M:%S") - timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M:%S')
        return starttime,endtime


    def get_parameters(self, verbose, starttime, endtime,
                       bbox, crs, format, lines, outputfile):

        parameters = {}        
        # get apikey from cnf-file 
        try:
            with open(CNFDIR + 'controller.cnf') as f:
                content = f.readlines()
                # remove white spaces and \n
                content = [x.strip() for x in content]
                # if first character is #, remove the line as a comment
                # save parameters as an array
                for x in content:
                    if(x[0] != '#'):
                        param = x.split('=')
                        if(param[0] == 'apikey'):
                            apikey = x.split('=', 1)

        except Exception as error:
            print(error)

        parameters.update({"verbose"    : verbose})
        parameters.update({"starttime"  : starttime})
        parameters.update({"endtime"    : endtime})
        parameters.update({"bbox"       : bbox})
        parameters.update({"projection" : crs})
        parameters.update({"format"     : format})
        parameters.update({"apikey"     : apikey})
        parameters.update({"lines"      : lines})
        parameters.update({"outputfile" : outputfile})
        
        return parameters


    
    # parse data from url
    def parse_data(self, parameters):
        
        starttime  = parameters['starttime']
        endtime    = parameters['endtime']
        bbox       = parameters['bbox']
        projection = parameters['projection']
        format     = parameters['format']
        apikey     = parameters['apikey'][1]
        lines      = parameters['lines']
        params     = "peak_current,multiplicity,cloud_indicator,ellipse_major"

        # check taht time stamps are valid
        starttime,endtime = self.check_date(starttime, endtime)

        url = ("http://data.fmi.fi/fmi-apikey/"+apikey+
               "/wfs?request=getFeature&storedquery_id=fmi::observations::lightning::simple"
               "&bbox="+bbox+
               "&parameters="+params+
               "&starttime="+starttime+
               "&endtime="+endtime
               )
        # disable system proxies
        urllib2.getproxies = lambda: {}
        # get data from url
        f = urllib2.urlopen(url,timeout=5)
        tree = ET.ElementTree(file=f)
        root = tree.getroot()
        f.close()
        
        # data contains 4 parameters which are displayed one
        # after another. These parameters have same timestamps
        # and coordinates, so those needs to be outputted only once
        # per observation.
        validparameters = ["peak_current", "multiplicity", "cloud_indicator", "ellipse_major"] 
        timestamps      = []
        values          = []
        coordinates     = []
        names           = []
        for first_child in root.iter("{http://xml.fmi.fi/schema/wfs/2.0}Time"):
            timestamps.append(first_child.text)
        for first_child in root.iter("{http://www.opengis.net/gml/3.2}pos"):
            coordinates.append(first_child.text)
        for first_child in root.iter("{http://xml.fmi.fi/schema/wfs/2.0}ParameterValue"):
            values.append(first_child.text)
        for first_child in root.iter("{http://xml.fmi.fi/schema/wfs/2.0}ParameterName"):
            names.append(first_child.text)

        # combine observations as one array:
        # 1) multiplicity, cloud_indicator ellipse_major
        # add timestamp and coordinates
        # 2) time lat lon peak_current multiplicity cloud_indicator ellipse_major
        index  = 0
        output = ""
        outputarray = []
        for i in xrange(0,len(values)):
            if(index == 4):
                outputarray.append(output)
                output = ""
                output = output + " " + values[i]
                index = 0
            elif(i==len(values)-1):
                output = output + " " + values[i]
                outputarray.append(output)
            else:
                output = output +" " + values[i]
            index = index + 1

        outputcoordinates = []
        outputtimes       = []
        for i in range(0, len(names), len(validparameters)):
            # remove possible leading and trailing spaces
            # and add every nth value to new arrays
            # i.e. 4 parameters, every 4th time and coordinate value
            cord = coordinates[i].strip()
            time = timestamps[i].strip()
            outputcoordinates.append(cord)
            outputtimes.append(time)

        output = []
        data   = ""
        for i in range(0, len(outputarray)):
            # remove leading and trailing spaces
            data = outputtimes[i]+" "+outputcoordinates[i]+" "+outputarray[i].strip()
            output.append(data)

        output = self.formatter(output, parameters['format'], lines)
        return output



    # inser data to database
    def insert_db(self, lightningArray):

        self.debug("Connect to database")
        # get connection settings from cnf-file
        try:
            with open(CNFDIR + 'controller.cnf') as f:
                content = f.readlines()
                # remove white spaces and \n
                content = [x.strip() for x in content]
                # if first character is #, remove the line as a comment
                # save parameters as an array
                for x in content:
                    if(x[0] != '#'):
                        param = x.split('=')
                        self.debug(param)
                        if(param[0] == 'host'):
                            host = x.split('=',1)
                        if(param[0] == 'user'):
                            user = x.split('=',1)
                        if(param[0] == 'password'):
                            password = x.split('=',1)
                        if(param[0] == 'database'):
                            database = x.split('=',1)
                        if(param[0] == 'port'):
                            port = x.split('=',1)
        except Exception as error:
            print(error)

        cnx = mysql.connector.connect(host=host[1], port=port[1], user=user[1],
                                      password=password[1], db=database[1])

        cursor = cnx.cursor(prepared="true")

        # add corresponding epoch time to data array
        lightning = list()
        for i in lightningArray:
            data  = i.split()
            epoch = int(time.mktime(datetime.strptime(data[0], "%Y-%m-%dT%H:%M:%SZ").timetuple()))
            data.append(epoch)
            lightning.append(data)

        add_lightning = ("INSERT INTO salama"
                         "(time, lat, lon, peakcurrent, multiplicity, cloudindicator, ellipsemajor, epoc) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)")

        # Insert lightning information
        self.debug("Add data to database")
        cursor.executemany(add_lightning, lightning)
        cnx.commit()

        cursor.close()
        cnx.close()
        
#if __name__ == '__main__':
    #salamiclass.run_class()

    

# testing
# test = salamiclass()    
# test.parse_data()
