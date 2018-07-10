import functools
import logging
import json
import urllib
#import re
#from operator import itemgetter
from google.appengine.api import urlfetch
#from google.appengine.ext import ndb
import time
import webapp2
from StringIO import StringIO
from zipfile import ZipFile
import xml.etree.ElementTree as etree
import os
import cloudstorage as gcs
from google.appengine.api import app_identity



localtime = time.asctime( time.localtime(time.time()) )
housetypes = ["hres", "hr", "hjres", "hconres"]
senatetypes = ["sres", "sjres", "sconres", "s"]

def writeFile(filename, myData):
    bucket_name = os.environ.get('BUCKET_NAME', app_identity.get_default_gcs_bucket_name())
    write_retry_params = gcs.RetryParams(backoff_factor=1.1)
    bucket = '/' + bucket_name
    myfilename = bucket + '/' + filename
    gcs_file = gcs.open(myfilename,
                  'w',
                  content_type='text/plain',
                  options={'x-goog-meta-foo': 'foo',
                           'x-goog-meta-bar': 'bar'},
                  retry_params=write_retry_params)
    gcs_file.write(myData)
    gcs_file.close()

def getFile(congress, chamber):
    bucket_name = os.environ.get('BUCKET_NAME', app_identity.get_default_gcs_bucket_name())
    bucket = '/' + bucket_name
    fetchfilenameStem = congress + '_' + chamber
    filename = bucket + '/' + fetchfilenameStem
    gcs_file = gcs.open(filename)
    contents = gcs_file.read()
    myJson = json.loads(contents)
    gcs_file.close()
    return myJson

def addItems(mydict, subject, member, sponsortype, howmany):
    if subject not in mydict:
        mydict[subject] = {}
    #if "total" in mydict[subject]:
    #    mydict[subject]["total"] += 1
    #else:
    #    mydict[subject]["total"] = 1
    if member not in mydict[subject]:
        mydict[subject][member] = {}
    if sponsortype in mydict[subject][member]:
        mydict[subject][member][sponsortype] += howmany
    else:
        mydict[subject][member][sponsortype] = howmany


def fetchZips(congress, chamber):
    def addSubject(subject, sponsors, cosponsors, type):
        if type == "policy":
            rootdict = allPolicies
        else:
            rootdict = dictSubjects
        #policyarea = policy.text.replace(" ","_")
        if subject not in rootdict:
            rootdict[subject] = {}
        if "total" in rootdict[subject]:
            rootdict[subject]["total"] += 1
        else:
            rootdict[subject]["total"] = 1
        for item in sponsors:
            bioidnode = item.find('bioguideId')
            if bioidnode is not None:
                bioid = bioidnode.text
                if bioid not in rootdict[subject]:
                    rootdict[subject][bioid] = {}
                if "sponsored" in rootdict[subject][bioid]:
                    rootdict[subject][bioid]["sponsored"] += 1
                else:
                    rootdict[subject][bioid]["sponsored"] = 1
        for item in cosponsors:
            withdrawn = item.find('sponsorshipWithdrawnDate').text
            if withdrawn is None:
                bioidnode = item.find('bioguideId')
                if bioidnode is not None:
                    bioid = bioidnode.text
                    if bioid not in rootdict[subject]:
                        rootdict[subject][bioid] = {}
                    if "cosponsored" in rootdict[subject][bioid]:
                        rootdict[subject][bioid]["cosponsored"] += 1
                    else:
                        rootdict[subject][bioid]["cosponsored"] = 1

    def parseZip(zf):
        for myname in zf.namelist():
            myfile = zf.read(myname)
            root = etree.fromstring(myfile)
            allsponsors = root.findall('.bill/sponsors/item')
            allcosponsors = root.findall('.bill/cosponsors/item')
            policynode = root.find('.//policyArea/name')
            if policynode is not None:
                policy = policynode.text.replace(" ","_")
                addSubject(policy, allsponsors, allcosponsors, "policy")
            allsubjects = root.findall('.//billSubjects/legislativeSubjects/item')
            for subitem in allsubjects:
                subject = subitem.find('name').text.replace(" ","_")
                addSubject(subject, allsponsors, allcosponsors, "legsubject")
            #testfetch.append(allsponsors)

    testfetch = []
    allHeadings = {}
    dictSubjects = {}
    allPolicies = {}
    if chamber == "house":
        locationList = housetypes
    if chamber == "senate":
        locationList = housetypes

    for mydir in locationList:
        try:
            validate_certificate = 'true'
            zipurl = "https://www.gpo.gov/fdsys/bulkdata/BILLSTATUS/" + congress + "/" + mydir + "/BILLSTATUS-" + congress + "-" + mydir + ".zip"
            result = urlfetch.fetch(zipurl)
            if result.status_code == 200:
                zf = ZipFile(StringIO(result.content))
                parseZip(zf)
            else:
                return result.status_code
        except urlfetch.Error:
                logging.exception('Caught exception fetching url')

    allHeadings["date_created"] = localtime
    allHeadings["legislative_subjects"] = dictSubjects
    allHeadings["policy_areas"] = allPolicies

    filenameStem = congress + "_" + chamber
    writeFile(filenameStem, json.dumps(allHeadings))
    #writeFile("subjectsbymember_" + filenameStem, json.dumps(dictSubjects))

    return "All done!"


class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write("mumbles...")
        self.response.write(localtime)
        bucket_name = os.environ.get('BUCKET_NAME', app_identity.get_default_gcs_bucket_name())
        self.response.write('Using bucket name: ' + bucket_name + '\n\n')


class BuildSubjects(webapp2.RequestHandler):
    def get(self):
        congress = self.request.get('congress')
        chamber = self.request.get('chamber')
        buildIt = fetchZips(congress, chamber)
        self.response.write(buildIt)

class BuildAllSubjects(webapp2.RequestHandler):
    def get(self):
        testarray = []
        congresses = ['113', '114', '115']
        allHouse = []
        houseTotals = {}
        houseTotals["date_created"] = localtime
        houseTotals["legislative_subjects"] = {}
        houseTotals["policy_areas"] = {}

        allSenate = []
        senateTotals = {}
        senateTotals["date_created"] = localtime
        senateTotals["legislative_subjects"] = {}
        senateTotals["policy_areas"] = {}

        for congress in congresses:
            myHresponse = getFile(congress, "house")
            allHouse.append(myHresponse)
            mySresponse = getFile(congress, "senate")
            allSenate.append(mySresponse)

        for houseDict in allHouse:
            for subject in houseDict["legislative_subjects"]:
                for member in houseDict["legislative_subjects"][subject]:
                    myboolean = isinstance(houseDict["legislative_subjects"][subject][member], dict)
                    if not myboolean:
                        testarray.append("False: " + subject + ": " + member)
                    #if houseDict["legislative_subjects"][subject][member]["cosponsored"] is not None:
                    #    testarray.append(houseDict["legislative_subjects"][subject][member]["cosponsored"])
                    #for sponsortype in houseDict["legislative_subjects"][subject]:
                        #testarray.append(sponsortype)
                    #if "cosponsored" in houseDict["legislative_subjects"][subject][member]:
                        #currentNum = houseDict["legislative_subjects"][subject][member]["cosponsored"]
                        #addItems(houseTotals["legislative_subjects"], subject, member, 'cosponsored', houseDict["legislative_subjects"][subject][member]["cosponsored"])
                    #if "sponsored" in houseDict["legislative_subjects"][subject][member]:
                    #    addItems(houseTotals["legislative_subjects"], subject, member, 'sponsored', houseDict["legislative_subjects"][subject][member]["sponsored"])

        self.response.write(testarray)


class FetchSubjects(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'application/json'
        bucket_name = os.environ.get('BUCKET_NAME', app_identity.get_default_gcs_bucket_name())
        bucket = '/' + bucket_name
        congress = self.request.get('congress')
        chamber = self.request.get('chamber')
        #subjecttype = self.request.get('subjecttype')
        fetchfilenameStem = congress + '_' + chamber
        filename = bucket + '/' + fetchfilenameStem

        gcs_file = gcs.open(filename)
        contents = gcs_file.read()
        gcs_file.close()
        self.response.write(contents)

app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/buildsubjects', BuildSubjects),
    ('/buildallsubjects', BuildAllSubjects),
    ('/fetchsubjects', FetchSubjects),

], debug=True)
