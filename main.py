import functools
import logging
import json
import urllib
from google.appengine.api import urlfetch
import time
import datetime
import webapp2
import xml.etree.ElementTree as etree
import os
import cloudstorage as gcs
import re
from google.appengine.api import app_identity

from google.appengine.ext import ndb
from StringIO import StringIO


localtime = time.asctime( time.localtime(time.time()) )
#congresses = ['113', '114', '115']

#api_key = "oZf7Bv5rp9AVB9PoT7hKpCcO2dt4j80nslXRp56N"
namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
modsnamespace = 'http://www.loc.gov/standards/mods/v3/mods.xsd'
todaysdate = datetime.date.today()

startcongress = 113
startcongressdate = datetime.date(2013, 1, 3)

def congresslist():
    mylist = [startcongress]
    diffdays = todaysdate - startcongressdate
    cycles = diffdays.days / 730
    newcongress = startcongress
    for x in range(0, cycles):
        newcongress = newcongress + 1
        mylist.append(newcongress)
    return mylist

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

def getFile(filename):
    bucket_name = os.environ.get('BUCKET_NAME', app_identity.get_default_gcs_bucket_name())
    bucket = '/' + bucket_name
    filename = bucket + '/' + filename
    gcs_file = gcs.open(filename)
    contents = gcs_file.read()
    gcs_file.close()
    return contents

class BillStatus(ndb.Model):
    #title = ndb.StringProperty()
    congress = ndb.StringProperty()
    type = ndb.StringProperty()
    sponsor = ndb.StringProperty()
    originalcosponsors = ndb.StringProperty(repeated=True)
    cosponsors = ndb.StringProperty(repeated=True)
    policy = ndb.StringProperty()
    legislativesubjects = ndb.StringProperty(repeated=True)

def handle_result(rpc):
    result = rpc.get_result()
    root = etree.fromstring(result.content)
    billnum = root.find('.bill/billNumber').text
    billtype = root.find('.bill/billType').text
    billcongress = root.find('.bill/congress').text
    billtitle = billcongress + billtype + billnum
    sponsor = root.find('.bill/sponsors/item/bioguideId')
    if sponsor is not None:
        billsponsor = sponsor.text
    else:
        billsponsor = ""
    cosponsorlist = []
    originalcosponsorlist = []
    allcosponsors = root.findall('.bill/cosponsors/item')
    for cosponsor in allcosponsors:
        withdrawn = cosponsor.find('sponsorshipWithdrawnDate').text
        if withdrawn is None:
            bioid = cosponsor.find('bioguideId').text
            if cosponsor.find('isOriginalCosponsor').text == "True":
                originalcosponsorlist.append(bioid)
            else:
                cosponsorlist.append(bioid)
    policynode = root.find('.//policyArea/name')
    if policynode is not None:
        billpolicy = policynode.text
    else:
        billpolicy = ""
    allsubjects = root.findall('.//billSubjects/legislativeSubjects/item')
    subjectlist = []
    for subitem in allsubjects:
        subject = subitem.find('name').text
        subjectlist.append(subject)
    mystatus = BillStatus(
    congress=billcongress, type=billtype, sponsor=billsponsor, originalcosponsors=originalcosponsorlist,
    cosponsors=cosponsorlist, policy=billpolicy, legislativesubjects=subjectlist,
    id=billtitle)
    mystatus.put()
rpcs = []


def fetchStatuses(urllist):
    badurls = []
    validate_certificate = 'true'
    for url in urllist:
        try:
            rpc = urlfetch.create_rpc(deadline=10000)
            rpc.callback = functools.partial(handle_result, rpc)
            urlfetch.make_fetch_call(rpc, url, validate_certificate=True)
            rpcs.append(rpc)
        except:
            badurls.append(url)

    for rpc in rpcs:
        rpc.wait()
    logging.info('Done waiting for RPCs')
    message = "Done!" + str(len(badurls)) + " bad URLs: " + str(badurls)
    return message


class MainPage(webapp2.RequestHandler):
    def get(self):
        counts = {}
        billtypes = ["sres", "sjres", "sconres", "s", "hres", "hr", "hjres", "hconres"]
        #congresses = ["113", "114", "115"]
        congresses = congresslist()
        self.response.headers['Content-Type'] = 'application/json'
        self.response.headers['Access-Control-Allow-Origin'] = '*'        #self.response.write(localtime)
        for congress in congresses:
            congress = str(congress)
            counts[congress] = {}
            for type in billtypes:
                total = BillStatus.query(BillStatus.congress == congress)
                total = total.filter(BillStatus.type == type.upper()).count()
                counts[congress][type] = total

        self.response.write(json.dumps(counts,indent=4))

class RebuildSubjects(webapp2.RequestHandler):
    def get(self):
        urllist = []
        del urllist[:]
        urllistpart = []
        del urllistpart[:]
        congress = self.request.get('congress')
        type = self.request.get('type')
        start = int(self.request.get('start'))
        resultsize = int(self.request.get('resultsize'))
        #this is kinda hacky, but much simpler than going back and forth through the API
        target = "https://www.gpo.gov/smap/bulkdata/BILLSTATUS/" + congress + type + "/sitemap.xml"
        validate_certificate = 'true'
        result = urlfetch.fetch(target)
        if result.status_code == 200:
            root = etree.fromstring(result.content)
            for loc in root.findall('.//s:loc', namespaces=dict(s=namespace)):
                urllist.append(loc.text)
        endpoint = start + resultsize
        urllistpart = urllist[start:endpoint]
        buildIt = fetchStatuses(urllistpart)
        myquery = BillStatus.query(BillStatus.congress == congress)
        myquery = myquery.filter(BillStatus.type == type.upper())
        count = myquery.count()
        self.response.write(buildIt)
        self.response.write(str(len(urllist)) + " source records. ")
        self.response.write(str(count) + " records added so far...")

class PutSingleBill(webapp2.RequestHandler):
    def get(self):
        myurl = self.request.get('url')
        congress = self.request.get('congress')
        type = self.request.get('type')
        billnum = self.request.get('billnum')
        if myurl:
            fetchStatuses([myurl])
            self.response.write("Success!")
        elif all([congress, type, billnum]):
            url = "https://www.gpo.gov/fdsys/bulkdata/BILLSTATUS/" +  congress + "/" + type + "/BILLSTATUS-" + congress + type + billnum + ".xml"
            fetchStatuses([url])
            self.response.write("Success!")
        else:
            self.response.write("Service to add individual bills to database.")
            self.response.write('''Syntax: either send FDSys url manually using 'url' or designate 'congress'
            'billnum' and 'type' (lowercase abbreviation)''')

class UpdateSubjects(webapp2.RequestHandler):
    def get(self):
        yesterday = todaysdate - datetime.timedelta(1)
        sourceurl = "https://www.govinfo.gov/rss/billstatus-batch.xml"
        validate_certificate = 'true'
        result = urlfetch.fetch(sourceurl)
        if result.status_code == 200:
            self.response.write("Success!")
            root = etree.fromstring(result.content)
            for item in root.findall('.//item'):
                pubdate = item.find('./pubDate').text
                #Python doesn't do time zones, but we don't actually need it
                itemdate = datetime.datetime.strptime(pubdate[:-6], '%a, %d %b %Y %H:%M:%S').date()
                description = item.find('./description').text
                if itemdate == yesterday:
                    urls = re.findall(r'<a href=(https://www.govinfo.gov/bulkdata/BILLSTATUS/\d+/[a-z]+/BILLSTATUS-[a-zA-Z0-9_]+.xml)>', description)
                    logging.info(len(urls))
                    updateIt = fetchStatuses(urls)
                    self.response.write(updateIt)

class BuildMembers(webapp2.RequestHandler):
    #This *almost* works, but as of jan 2019, there are inconsistencies with the source data
    #Will try again with the next formal release from GPO
    def get(self):
        self.response.headers['Content-Type'] = 'application/json'

        def getMembers(packageId):
            sourceurl = "https://api.govinfo.gov/packages/" + packageId + "/mods?api_key=oZf7Bv5rp9AVB9PoT7hKpCcO2dt4j80nslXRp56N"
            logging.info(sourceurl)
            validate_certificate = 'true'
            result = urlfetch.fetch(sourceurl)
            if result.status_code == 200:
                root = etree.fromstring(result.content)
                currentversion = root.find('.{http://www.loc.gov/mods/v3}extension/{http://www.loc.gov/mods/v3}isCurrentEdition').text
                congelements = root.findall('.//{http://www.loc.gov/mods/v3}extension[{http://www.loc.gov/mods/v3}congMember]')
                for congelement in congelements:
                    district = congelement.find('.{http://www.loc.gov/mods/v3}district')
                    if district is not None:
                        district = district.text
                    congmember = congelement.find('.{http://www.loc.gov/mods/v3}congMember')
                    bioid = congmember.get("bioGuideId")
                    state = congmember.get("state")
                    party = congmember.get("party")
                    mychamber = congmember.get("chamber")
                    mycongress = congmember.get("congress")
                    names = congmember.findall(".//{http://www.loc.gov/mods/v3}name")
                    for name in names:
                        if name.get('type') == "authority-fnf":
                            pname = name.text
                        if name.get('type') == "authority-lnf":
                            sname = name.text
                    #have to deal with missing bioGuideIds until GPO fixes their script
                    if bioid is not None:
                        pass
                    else:
                        logging.info(sname)
                        bioid = sname
                    allmembers.setdefault(bioid, { "pname": pname, "sname": sname, "state": state, "party": party })
                    if district:
                        allmembers[bioid]["district"] = district
                    allmembers[bioid].setdefault(mychamber, [])
                    if mycongress in allmembers[bioid][mychamber]:
                        break
                    else:
                        allmembers[bioid][mychamber].append(mycongress)
                    if currentversion == "true":
                        allmembers[bioid]["currentmember"] = "TRUE"

        allmembers = {}
        sourceurl = "https://api.govinfo.gov/collections/CDIR/2018-01-28T20%3A18%3A10Z?offset=0&pageSize=100&api_key=oZf7Bv5rp9AVB9PoT7hKpCcO2dt4j80nslXRp56N"
        validate_certificate = 'true'
        result = urlfetch.fetch(sourceurl)
        if result.status_code == 200:
            linklist = json.loads(result.content)
            for package in linklist["packages"]:
                packagedate = datetime.datetime.strptime(package["packageId"][5:], '%Y-%m-%d').date()
                if packagedate >= startcongressdate:
                    getMembers(package["packageId"])

        self.response.write(json.dumps(allmembers,indent=4))
        writeFile("allmembers", json.dumps(allmembers))


class FetchMemberList(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'application/json'
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        myJson = getFile("allmembers")
        self.response.write(myJson)

class BuildSubjectList(webapp2.RequestHandler):
    def get(self):
        policies = []
        legislativesubjects = set()
        congresses = congresslist()
        subjectList = { "policies": {}, "legislativesubjects": {} }
        distinctpolicy = BillStatus.query(projection=["policy"],distinct=True)
        for result in distinctpolicy:
            policies.append(result.policy)

        getsubjects = BillStatus.query(projection=["legislativesubjects"],distinct=True)
        for result in getsubjects:
            subjects = result.legislativesubjects
            for subject in subjects:
                legislativesubjects.add(subject)

        for policy in policies:
            subjectList["policies"][policy] = {}
            mytotal = BillStatus.query(BillStatus.policy == policy)
            subjectList["policies"][policy]['total'] = mytotal.count()
            for congress in congresses:
                subjectList["policies"][policy][str(congress)] = mytotal.filter(BillStatus.congress == str(congress)).count()

        for subject in legislativesubjects:
            subjectList["legislativesubjects"][subject] = {}
            mytotal = BillStatus.query(BillStatus.legislativesubjects == subject)
            subjectList["legislativesubjects"][subject]['total'] = mytotal.count()
            for congress in congresses:
                subjectList["legislativesubjects"][subject][str(congress)] = mytotal.filter(BillStatus.congress == str(congress)).count()

        self.response.headers['Content-Type'] = 'application/json'
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.write(json.dumps(subjectList,indent=4))
        writeFile("subjectList", json.dumps(subjectList))

class FetchSubjectList(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'application/json'
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        myJson = getFile("subjectList")
        self.response.write(myJson)


class FetchSubject(webapp2.RequestHandler):
    def get(self):

        def addMember(member, sponsortype):
            subjdict["members"].setdefault(member,{})
            if sponsortype in subjdict["members"][member]:
                subjdict["members"][member][sponsortype] += 1
            else:
                subjdict["members"][member][sponsortype] = 1

        subjdict = { "members": {} }
        congress = self.request.get('congress')
        chamber = self.request.get('chamber')
        subjecttype = self.request.get('subjecttype')
        subject = self.request.get('subject')
        if subjecttype == "policy":
            myquery = BillStatus.query(BillStatus.policy == subject)
        elif subjecttype == "legsubject":
            myquery = BillStatus.query(BillStatus.legislativesubjects == subject)
        if chamber == "house":
            billtypes = ["HRES", "HR", "HJRES", "HCONRES"]
        elif chamber == "senate":
            billtypes = ["SRES", "SJRES", "SCONRES", "S"]
        myquery = myquery.filter(BillStatus.type.IN(billtypes))
        if congress:
            myquery = myquery.filter(BillStatus.congress == congress)
        results = myquery.fetch()

        for status in results:
            addMember(status.sponsor, "sponsored")
            for originalcosponsor in status.originalcosponsors:
                addMember(originalcosponsor, "originalcosponsored")
            for cosponsor in status.cosponsors:
                addMember(cosponsor, "cosponsored")
        self.response.headers['Content-Type'] = 'application/json'
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.write(json.dumps(subjdict,indent=4))

class FetchMember(webapp2.RequestHandler):
    def get(self):

        def addSubject(subject, subjecttype, sponsortype):
            memberdict[subjecttype].setdefault(subject,{})
            if sponsortype in memberdict[subjecttype][subject]:
                memberdict[subjecttype][subject][sponsortype] += 1
            else:
                memberdict[subjecttype][subject][sponsortype] = 1

        memberdict = { "legsubjects": {}, "policies": {} }
        member = self.request.get('member')
        congress = self.request.get('congress')
        myquery =  BillStatus.query(ndb.OR(BillStatus.sponsor == member,
                             BillStatus.cosponsors == member,
                             BillStatus.originalcosponsors == member))
        if congress:
            myquery = myquery.filter(BillStatus.congress == congress)
        results = myquery.fetch()

        for status in results:
            if member == status.sponsor:
                sponsortype = "sponsored"
            if member in status.cosponsors:
                sponsortype = "cosponsored"
            if member in status.originalcosponsors:
                sponsortype = "originalcosponsored"
            addSubject(status.policy, "policies", sponsortype)
            for subject in status.legislativesubjects:
                addSubject(subject, "legsubjects", sponsortype)

        self.response.headers['Content-Type'] = 'application/json'
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.write(json.dumps(memberdict,indent=4))


class ShowRecords(webapp2.RequestHandler):
    def get(self):
        if self.request.get('key'):
            bills = [BillStatus.get_by_id(self.request.get('key'))]
        else:
            bills = BillStatus.query()
            if self.request.get('congress'):
                bills = bills.filter(BillStatus.congress == self.request.get('congress'))
            if self.request.get('type'):
                bills = bills.filter(BillStatus.type == self.request.get('type'))
            if self.request.get('policy'):
                bills = bills.filter(BillStatus.policy == self.request.get('policy'))
            if self.request.get('subject'):
                bills = bills.filter(BillStatus.legislativesubjects == self.request.get('subject'))
            if self.request.get('sponsor'):
                bills = bills.filter(BillStatus.sponsor == self.request.get('sponsor'))
            if self.request.get('originalcosponsors'):
                bills = bills.filter(BillStatus.originalcosponsors == self.request.get('originalcosponsors'))
            if self.request.get('cosponsors'):
                bills = bills.filter(BillStatus.cosponsors == self.request.get('cosponsors'))


        for bill in bills:
            billId = bill.key.id()
            self.response.write(bill)
            self.response.write("<br /><br />")


app = webapp2.WSGIApplication([
    ('/', MainPage),
    #('/buildmemberlist', BuildMembers),
    ('/fetchmembers', FetchMemberList),
    ('/buildsubjectlist', BuildSubjectList),
    ('/listsubjects', FetchSubjectList),
    ('/recordcheck', ShowRecords),
    ('/rebuildsubjects', RebuildSubjects),
    ('/updatesubjects', UpdateSubjects),
    ('/subjectsearch', FetchSubject),
    ('/membersearch', FetchMember),
    ('/addsingle', PutSingleBill),

], debug=True)
