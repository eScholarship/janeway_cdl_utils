from django.conf import settings as django_settings
from django.core.management.base import BaseCommand
import requests
import datetime
import json
import urllib.request
import os
import django.utils.timezone
from submission import models as submission_models
from repository import models as repository_models
from core import models as core_models
from django.template.defaultfilters import slugify
from uuid import uuid4

PRESS_ID = 1
REPO_ID = 3
COI_ID = 1
NODATA_ID = 1
NUMD_ID = 1

class Command(BaseCommand):
    """
    Pulls data from COS and adds to DB.
    """

    help = "Deletes duplicate settings."

    def handle(self, *args, **options):
        print("import eer data")
        if self.check_prereq() == False:
            return

        print(django_settings.OSF_TOKEN)
        #only do this doi switch once
        #self.switchdoi()
        w = Worker()

        
        num = 1

    def switchdoi(self):
        print("switching from doi to preprint doi")
        allobj = repository_models.Preprint.objects.all()
        for obj in allobj:
            obj.preprint_doi = obj.doi
            obj.doi = None
            obj.save()
        print("done with doi switch")

    def check_prereq(self):
        print("checking prereq")
        if django_settings.OSF_TOKEN is None:
            print("add OSF token to settings to proceed")
            return False

        # get repository
        global REPO_ID
        global PRESS_ID
        global COI_ID
        global NODATA_ID
        global NUMD_ID

        # TBD - fix this check
        repo = repository_models.Repository.objects.get(name='EcoEvoRxiv')
        REPO_ID = repo.id
        PRESS_ID = repo.press_id
        COI_ID = repository_models.RepositoryField.objects.get_or_create(name='conflict_of_interest_statement', input_type='text', defaults={'required':0, 'order':1, 'display':0, 'repository_id':REPO_ID })[0].id
        NODATA_ID = repository_models.RepositoryField.objects.get_or_create(name='why_no_data', input_type='text', defaults={'required':0, 'order':2, 'display':0, 'repository_id':REPO_ID })[0].id
        NUMD_ID = repository_models.RepositoryField.objects.get_or_create(name='num_downloads', input_type='text', defaults={'required':0, 'order':3, 'display':0, 'repository_id':REPO_ID })[0].id

        return True


############################################################
class OSF:
    
    url_provides = "https://api.osf.io/v2/preprint_providers"

    eer_search = "https://api.osf.io/v2/preprints/?filter[provider]=ecoevorxiv"
    #https://api.osf.io/v2/preprints/?filter[provider]=ecoevorxiv&filter[date_created][gte]=2020-05-30
    #"https://api.osf.io/v2/preprints/?filter[provider]=ecoevorxiv"

    headers = {'Content-Type': 'application/json',
             'Authorization': 'Bearer {0}'.format(django_settings.OSF_TOKEN)}

    def getProviders(self):
        resp = requests.get(self.url_provides, headers=self.headers)
        return resp.text

    def getItems(self, url):
        if url is None:
            resp = requests.get(self.eer_search, headers=self.headers)
        else:
            resp = requests.get(url, headers=self.headers)
        return resp.json()

    def getData(self, url):
        resp = requests.get(url, headers=self.headers)
        return resp.json()

############################################################

class License:
    id = ''
    name = ''
    url = ''
    text = ''
    lic = None
    order=0
    def __init__(self, data):
        #print(data)
        if not (data.get("data") is None):
            License.order += 1
            self.extractData(data["data"])

    def extractData(self, data):
        self.id = data["id"]
        self.name = data["attributes"]["name"]
        self.text = data["attributes"]["text"]
        self.url = data["attributes"]["url"]
        self.isValid = True
        self.lic = submission_models.Licence.objects.get_or_create(name=self.name, defaults={'short_name':self.name, 'url':self.url, 'text':self.text, 'press_id':PRESS_ID, 'order':License.order })[0]

############################################################

class Subjects:
    arr = {}
    def __init__(self, data):
        self.arr = {}
        #print(datastr)
        #data = json.loads(datastr)
        # get subject out of attributes
        if not (data.get("subjects") is None):
            self.extractData(data["subjects"])

    def extractData(self, data):
        for i in range(len(data)):
            prev = None
            for j in range(len(data[i])):
                if data[i][j].get('text') is not None:
                    #self.arr.append(data[i][j]['text'])
                    subject = data[i][j]['text']
                    result = repository_models.Subject.objects.get_or_create(name=subject, repository_id=REPO_ID, parent_id=prev, defaults={'slug':slugify(subject)})[0]
                    prev = result.id
                    if result.id not in self.arr:
                        self.arr[result.id] = result



############################################################

class Tags:
    arr = []
    def __init__(self, data):
        self.arr = []
        print(data)
        # get subject out of attributes
        if not (data.get("tags") is None):
            self.extractData(data["tags"])

    def extractData(self, data):
        for i in range(len(data)):
            self.arr.append(data[i])

############################################################

class Authors:
    arr = []
    owner = None
    def __init__(self, data, pp):
        self.arr = []
        self.owner = None
        print(data)
        # get subject out of attributes
        for i in range(len(data['data'])):
            # data['embeds']['users']['data']['id']
            # skip the authors where data is not availalbe
            if 'embeds' in data['data'][i] and 'users' in data['data'][i]['embeds'] and 'data' in data['data'][i]['embeds']['users']:
                self.arr.append(authorItem(data['data'][i]))
            else:
                print("SKIPPING Author - Missing data")
        self.saveData(pp)

    def saveData(self, pp):
        for i in range(len(self.arr)):
            print("lets save here")
            auth = self.arr[i]
            result_auth = repository_models.Author.objects.get_or_create(email_address=auth.email, defaults={'first_name':auth.first, 'middle_name':auth.middle, 'last_name': auth.last, 'orcid':auth.orcid})[0]

            print("creating account for the author")
            result_acc = core_models.Account.objects.get_or_create(email=auth.email, username=auth.email, defaults={'password':auth.email, 'is_superuser': 0, 
                                                                                                        'first_name':auth.first, 'middle_name':auth.middle, 'last_name':auth.last,
                                                                                                        'institution':'x', 'is_active':1, 'is_staff':0, 'is_admin':0, 
                                                                                                        'enable_digest':0, 'enable_public_profile':0, 
                                                                                                        'date_joined': django.utils.timezone.now, 'uuid':uuid4()})[0]
            result_acc.set_password(auth.email)
            result_acc.save()

            #link here
            repository_models.PreprintAuthor.objects.get_or_create(author_id=result_auth.id, preprint_id=pp.id, account_id = result_acc.id, defaults={'order': auth.order})
            
            if auth.active is True and self.owner is None:
                self.owner = result_acc.id

############################################################

class authorItem:
    #extract key info from osf entry
    osfId = ""
    full=""
    first="" 
    last="" 
    middle=""
    order="" 
    orcid=""
    email=""
    active=False
    def __init__(self, data):
        #print("extract key info here")
        self.osfId = data['embeds']['users']['data']['id']
        self.full=data['embeds']['users']['data']['attributes']['full_name']
        self.first=data['embeds']['users']['data']['attributes']['given_name']
        self.last=data['embeds']['users']['data']['attributes']['family_name']
        self.middle=data['embeds']['users']['data']['attributes']['middle_names']
        self.active=data['embeds']['users']['data']['attributes']['active']
        
        self.order = data['attributes']['index']
        d = json.loads('{}')
        self.orcid=data['embeds']['users']['data']['attributes'].get('social',d).get('orcid',None)
        self.email = self.osfId + '@ecoevorxiv.org'

############################################################

############################################################

class EarthItem:
    osfId=""
    type="" 
    attr="" 
    pp_doi=""
    rels="" 
    license=""
    contributors=""
    primaryFile="" 
    files=""
    data=None
    def __init__(self, data):
        print("extract key info here")
        self.osfId=data['id']
        self.type=data['type'] 
        self.pp_doi=data['links']['preprint_doi'].split("doi.org/")[1]
        #self.attr=json.dumps(data['attributes']).replace('\'','')
        #self.rels=json.dumps(data['relationships']).replace('\'','')
        self.attr=data['attributes']
        self.rels=data['relationships']
        d = json.loads('{}')
        self.license=data['relationships'].get('license',d).get('links',d).get('related',d).get('href','')
        self.contributors=data['relationships'].get('contributors',d).get('links',d).get('related',d).get('href','')
        self.primaryFile=data['relationships'].get('primary_file',d).get('links',d).get('related',d).get('href','')
        self.files=data['relationships'].get('files',d).get('links',d).get('related',d).get('href','')
        if self.pp_doi is None or len(self.pp_doi) < 10:
            print("overriding pp doi with osfid since it is used to id of article")
            self.pp_doi = self.osfId
        self.data = None
        typedata = data['relationships'].get('node',d).get('data',d)
        if typedata:
            type = typedata.get('type','')
            if type == 'nodes':
                self.data = typedata.get('id','')

############################################################


class Article:
    #extract other info from osf entry
    #x=datetime.datetime(2020,1,1).today()
    d="2000-01-01T11:11:11.12345"
    #f="%Y-%m-%d %H:%M:%S"
    f="%Y-%m-%dT%H:%M:%S+00:00"
    fi="%Y-%m-%dT%H:%M:%S.%f"
    dateCreated="" 
    dateModified="" 
    datePublished="" 
    dateDoiCreated="" 
    reviewState="" 
    is_published=False
    data_links=[]  #NEW
    title=''
    desc=''
    pp = None
    doi = None     #NEW - done
    why_no_data = None #NEW
    conflict_of_interest_statement = None
    def __init__(self, eItem, licId):
        print("extract item info here")
        self.extractData(eItem.attr)
        self.pp = None
        if self.reviewState != 'withdrawn':
            # update the identity column
            self.pp = repository_models.Preprint.objects.get_or_create(preprint_doi=eItem.pp_doi, defaults={'stage':'preprint_published', 'title':self.title, 'abstract': self.desc, 'current_step':5,
                                                                                                   'comments_editor':self.reviewState, 'preprint_decision_notification':1, 'repository_id':REPO_ID, 
                                                                                                   'license_id':licId, 'date_started':self.dateCreated, 'date_accepted':self.datePublished,
                                                                                                   'date_published':self.datePublished,'date_submitted':self.dateCreated, 'date_updated':self.dateModified})[0]
        
            self.fillData(eItem)
            self.saveExtras()
        else:
            print("skipping WITHDRAWN " + eItem.osfId)
            

    def fillData(self, eItem):
        print("fill data if present and published doi")
        if self.doi:
            # append 'https://doi.org/' to the doi
            self.pp.doi = 'https://doi.org/' + self.doi
        num = 0
        if eItem.data is not None:
            num += 1
            repository_models.PreprintSupplementaryFile.objects.get_or_create(preprint_id=self.pp.id, url = 'https://osf.io/'+eItem.data, defaults={'label':'Supplementary material', 'order':num})

        if self.data_links:
            for link in self.data_links:
                #create a link
                num += 1
                repository_models.PreprintSupplementaryFile.objects.get_or_create(preprint_id=self.pp.id, url = link, defaults={'label':'Public data', 'order':num})

    def saveExtras(self):
        print("save extras in field/answer")
        
        if self.why_no_data is not None and self.why_no_data != '':
            repository_models.RepositoryFieldAnswer.objects.get_or_create(preprint_id=self.pp.id, field_id = NODATA_ID, defaults={'answer': self.why_no_data})

        if self.conflict_of_interest_statement is not None:
            repository_models.RepositoryFieldAnswer.objects.get_or_create(preprint_id=self.pp.id, field_id = COI_ID, defaults={'answer': self.conflict_of_interest_statement})



    def extractData(self,data):
        self.dateCreated = data['date_created'] or self.d
        self.dateModified = data['date_modified'] or self.d
        self.datePublished = data['date_published'] or self.d
        self.dateDoiCreated = data['preprint_doi_created'] or self.d
        self.dateCreated = datetime.datetime.strptime(self.dateCreated, self.fi).strftime(self.f)
        self.dateModified = datetime.datetime.strptime(self.dateModified, self.fi).strftime(self.f)
        self.datePublished = datetime.datetime.strptime(self.datePublished, self.fi).strftime(self.f)
        self.dateDoiCreated = datetime.datetime.strptime(self.dateDoiCreated, self.fi).strftime(self.f)
        self.reviewState=data['reviews_state'] 
        self.is_published=data.get('is_published',False) or False
        self.data_links=data['data_links']
        self.why_no_data=data['why_no_data']
        self.conflict_of_interest_statement = data['conflict_of_interest_statement']
        self.title=data['title'].replace('\'','')
        self.desc=data['description'].replace('\'','')
        self.doi=data['doi']

############################################################
class Version:
    d="2000-01-01T11:11:11.12345"
    f="%Y-%m-%dT%H:%M:%S+00:00"
    fi="%Y-%m-%dT%H:%M:%S.%f"
    #extract file info
    osfId=""
    name=""
    size=0
    dateCreated="" 
    downloadLink=""
    fileext="pdf"
    pf = None
    pv = None
    oldpath = ''

    def __init__(self, data, pp, parentId):
        print("extract version here")
        self.extractData(data)
        self.saveFile(pp, parentId)
            

    def saveFile(self, pp, parentId):
        if len(self.downloadLink) > 10:
            ext = os.path.splitext(self.name)
            oldname = parentId + ext[1]
            savename = parentId + "_" + self.osfId + ext[1]
            repoPath = os.path.join('repos', str(pp.id), savename)
            self.oldpath = os.path.join('repos', str(pp.id), oldname)
            downloadPath = os.path.join(django_settings.BASE_DIR, 'files', 'repos', str(pp.id))
            #save using the download link
            try:
                self.downloadFile(downloadPath, savename)
                mime = 'application/pdf'
                if ext[1] != '.pdf':
                    mime = 'application/msword'
            
                self.pf = repository_models.PreprintFile.objects.get_or_create(file=repoPath, defaults={'original_filename':self.name,'uploaded':self.dateCreated, 
                                                                                                        'mime_type':mime, 'size':self.size, 'preprint_id':pp.id })[0]
            
                self.pv = repository_models.PreprintVersion.objects.get_or_create(file_id=self.pf.id, preprint_id=pp.id, defaults={'version':self.osfId, 'date_time': self.dateCreated})[0]
            except Exception as e:
                print(str(e))

    def downloadFile(self, path, name):
        print(self.downloadLink)
        if not os.path.exists(path):
            os.makedirs(path)
        savepath = os.path.join(path, name)
        response = urllib.request.urlretrieve(self.downloadLink, savepath)

    def extractData(self,data):
        self.osfId=data['id']
        self.name=data['attributes']['name'].replace('\'','')
        self.size=data['attributes']['size']
        self.dateCreated=data['attributes']['date_created'] or self.d
        
        self.dateCreated = datetime.datetime.strptime(self.dateCreated, self.fi).strftime(self.f)
        self.downloadLink=data['links']['download']



############################################################
class VersionFiles:
    arr:[]
    id:''
    name:''
    downloads:'' # NEW
    current_version:''
    def __init__(self, data, osf, pp):
        print("get the osfstorage link")
        self.arr=[]
        if not (data.get("data") is None):
            osfstorage = data["data"][0]["relationships"]["files"]["links"]["related"]["href"]
            #get the osfstorage
            storage = osf.getData(osfstorage)
            if not (storage.get("data") is None):
                self.extractData(storage["data"], osf, pp)

    def extractData(self, data, osf, pp):
        self.id = data[0]["id"]
        self.name = data[0]["attributes"]["name"]
        self.downloads = data[0]["attributes"]["extra"]["downloads"]
        self.current_version = str(data[0]["attributes"]["current_version"])
        versions = data[0]["relationships"]["versions"]["links"]["related"]["href"]
        self.extractVersions(osf.getData(versions), pp)
        self.filldownloads(pp)

    def extractVersions(self, data, pp):
        for i in range(len(data["data"])):
            self.arr.append(Version(data["data"][i], pp, self.id))
            if self.arr[i].osfId == self.current_version:
                print("save submission and version info here")
                # get the file and version ids from the current version and attach to pp
                pp.submission_file_id = self.arr[i].pf.id
                #pp.curent_version_id = self.arr[i].pv.id

    def filldownloads(self, pp):
        print("fill the number of downloads so far")
        if self.downloads:
            repository_models.RepositoryFieldAnswer.objects.get_or_create(preprint_id=pp.id, field_id = NUMD_ID, defaults={'answer': self.downloads})


############################################################

class Worker:
    allLicenses = {}

    osf = OSF()
    def __init__(self):

        print("lets get the list of all licenses")
        # create a dictionary of OSF id and License       
        next = self.osf.eer_search
        #count = 0
        while next is not None:
            data = self.osf.getItems(next)
            next = data['links']['next']
            #if count > 3:
            #    next = None
            #count += 1

            for i in range(len(data['data'])):
                a = EarthItem(data['data'][i])
                licId = self.getLicense(a)                
                pp = self.getArticle(a, licId)
                if pp is not None:
                    self.processArticle(a, pp)

        self.deleteWithdrawn()


    def processArticle(self, a, pp):
        files = self.getAllVersions(a, pp)
        self.getSubjects(a, pp)
        self.getTags(a, pp)
        auths = self.getAuthors(a, pp)
        pp.owner_id = auths.owner
        if files is None:
            pp.date_accepted = None
            pp.date_published = None
            pp.current_step = 1
        pp.save()

    def deleteWithdrawn(self):
        #find all the entries with withdrawn 
        allobj = repository_models.Preprint.objects.filter(comments_editor='withdrawn')
        for obj in allobj:
            obj.delete()


    def getLicense(self, a):      
        if a.license in self.allLicenses:
            return self.allLicenses[a.license]

        if len(a.license) > 10:
            l = License(self.osf.getData(a.license))
            self.allLicenses[a.license] = l.lic.id
            return l.lic.id

        return None
                

    #pass pp here so relations can be set inside
    def getTags(self, a, pp):       
        tags = Tags(a.attr)
        for i in range(len(tags.arr)):
            result = submission_models.Keyword.objects.get_or_create(word=tags.arr[i])[0]
            if pp.keywords.filter(pk=result.id).exists() is False:
                pp.keywords.add(result)

    #pass article so that connections can be done here
    def getSubjects(self, a, pp): 
        subs = Subjects(a.attr)
        for x in subs.arr:
            if pp.subject.filter(pk=x).exists() is False:
                pp.subject.add(subs.arr[x])

    #pass article so that connections can be done here
    def getAuthors(self, a, pp): 
        print("get authors")
        if len(a.contributors) > 10:
            return Authors(self.osf.getData(a.contributors),pp)
        return None

    def getPrimaryFile(self, a, pp): 
        print("get primary file")
        if len(a.primaryFile) > 10:
            return PrimaryFile(self.osf.getData(a.primaryFile), pp)
        return None


    def getArticle(self, a, licId): 
        pp = Article(a, licId)
        return pp.pp

    def getAllVersions(self, a, pp):
        print("get all versions")
        if len(a.files) > 10:
            return VersionFiles(self.osf.getData(a.files), self.osf, pp)
        return None


            
