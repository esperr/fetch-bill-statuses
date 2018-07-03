import functools
import logging
import json
import urllib
import re
#from operator import itemgetter
from google.appengine.api import urlfetch
from google.appengine.ext import ndb
import time
import webapp2
from StringIO import StringIO
from zipfile import ZipFile
import xml.etree.ElementTree as etree
import os
import cloudstorage as gcs
from google.appengine.api import app_identity


#import zipfile

localtime = time.asctime( time.localtime(time.time()) )
housetypes = ["hres", "hr", "hjres", "hconres"]
senatetypes = ["sres", "sjres", "sconres", "s"]

def storeJson(mykey, myData):
    gotJson = myJson.query(myJson.applicationName==mykey).fetch()
    if len(gotJson) > 0:
        baseline = gotJson[0]
        baseline.json = myData
        baseline.put()
    else:
        baselinejson = myJson(applicationName=mykey, json=myData)
        baselinejson.put()

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

    mykeystem = congress + "-" + chamber
    storeJson(mykeystem + "-policies", json.dumps(allPolicies))
    storeJson(mykeystem + "-subjects", json.dumps(dictSubjects))

    return "All done!"
        #yearCounts['counts'] = sorted(yearCounts['counts'], key=itemgetter('year'))
    #prettiness = json.dumps(yearCounts, sort_keys=True, indent=4)
    #return prettiness

class myJson(ndb.Model):
    applicationName = ndb.StringProperty()
    json = ndb.TextProperty()

class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write("mumbles...")
        self.response.write(localtime)
        bucket_name = os.environ.get('BUCKET_NAME', app_identity.get_default_gcs_bucket_name())
        self.response.write('Using bucket name: ' + bucket_name + '\n\n')
        #mystatus = fetchZips("113", "house")
        #self.response.write(mystatus)

class BuildBaseCounts(webapp2.RequestHandler):
    def get(self):
        congress = self.request.get('congress')
        chamber = self.request.get('chamber')
        buildIt = fetchZips(congress, chamber)
        self.response.write(buildIt)


app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/buildbasecounts', BuildBaseCounts),
], debug=True)
