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
import xml.etree.ElementTree as etree
import os
import cloudstorage as gcs
from google.appengine.api import app_identity



localtime = time.asctime( time.localtime(time.time()) )
congresses = ['113', '114', '115']
housetypes = ["hres", "hr", "hjres", "hconres"]
senatetypes = ["sres", "sjres", "sconres", "s"]
#api_key = "oZf7Bv5rp9AVB9PoT7hKpCcO2dt4j80nslXRp56N"
namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
billarray = []
billset = set()
allHeadings = {}
dictSubjects = {}
allPolicies = {}


def handle_result(rpc):
    result = rpc.get_result()
    root = etree.fromstring(result.content)
    title = root.find('.bill/billNumber').text
    billarray.append(title)
    billset.add(title)
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
    #logging.info('Handling RPC in callback')

rpcs = []

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

def addItems(mydict, subject, member, sponsortype, howmany):
    if subject not in mydict:
        mydict[subject] = {}
    if member not in mydict[subject]:
        mydict[subject][member] = {}
    if sponsortype in mydict[subject][member]:
        mydict[subject][member][sponsortype] += howmany
    else:
        mydict[subject][member][sponsortype] = howmany

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
    gcs_file.close()
    myJson = json.loads(contents)
    return myJson

def fetchStatuses(targetList):


    def parseFiles(listFiles):
        pass

        #testfetch.append(allsponsors)

    for target in targetList:
        try:
            validate_certificate = 'true'
            result = urlfetch.fetch(target)
            if result.status_code == 200:
                root = etree.fromstring(result.content)
                for loc in root.findall('.//s:loc', namespaces=dict(s=namespace)):
                    url = loc.text
                    rpc = urlfetch.create_rpc(deadline=300)
                    rpc.callback = functools.partial(handle_result, rpc)
                    urlfetch.make_fetch_call(rpc, url)
                    rpcs.append(rpc)
            else:
                return result.status_code
        except urlfetch.Error:
                logging.exception('Caught exception fetching url')

    #allHeadings["date_created"] = localtime
    #allHeadings["legislative_subjects"] = dictSubjects
    #allHeadings["policy_areas"] = allPolicies

    #return statusFiles
    for rpc in rpcs:
        rpc.wait()

    logging.info('Done waiting for RPCs')


class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write("mumbles...")
        self.response.write(localtime)
        bucket_name = os.environ.get('BUCKET_NAME', app_identity.get_default_gcs_bucket_name())
        self.response.write('Using bucket name: ' + bucket_name + '\n\n')


class BuildSubjects(webapp2.RequestHandler):
    def get(self):
        start = time.time()
        targetList = []
        congress = self.request.get('congress')
        chamber = self.request.get('chamber')
        #moving the directory picking logic to here
        if chamber == "house":
            locationList = housetypes
        if chamber == "senate":
            locationList = senatetypes

        for location in locationList:
            fileList = "https://www.gpo.gov/smap/bulkdata/BILLSTATUS/" + congress + location + "/sitemap.xml"
            #fileList = "https://www.govinfo.gov/bulkdata/json/BILLSTATUS/" + congress + "/" + location
            targetList.append(fileList)
        testtargets = ["https://www.gpo.gov/smap/bulkdata/BILLSTATUS/114hr/sitemap.xml"]
        buildIt = fetchStatuses(testtargets)
        #filenameStem = congress + "_" + chamber
        #writeFile(filenameStem, json.dumps(buildIt))

        end = time.time()
        self.response.write(end - start)
        self.response.write("Set: " +  str(len(billset)))
        self.response.write("Array: " + str(len(billarray)))


class BuildAllSubjects(webapp2.RequestHandler):
        def get(self):
            chamber = self.request.get('chamber')
            targetList = []

            if chamber == "house":
                locationList = housetypes
            if chamber == "senate":
                locationList = senatetypes

            for location in housetypes:
                for congress in congresses:
                    zipurl = "https://www.gpo.gov/fdsys/bulkdata/BILLSTATUS/" + congress + "/" + location + "/BILLSTATUS-" + congress + "-" + location + ".zip"
                    targetList.append(zipurl)

            buildIt = fetchZips(targetList)
            filenameStem = "all" + "_" + "house"
            writeFile(filenameStem, json.dumps(buildIt))
            self.response.write("All done!")


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
