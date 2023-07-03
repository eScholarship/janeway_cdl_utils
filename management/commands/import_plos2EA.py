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
from django.core.mail import send_mail

import xml.etree.ElementTree as ET
from ftplib import FTP_TLS
from datetime import datetime
import traceback
import sys
import html

PRESS_ID = 1
REPO_ID = 1
COI_ID = 1
DATA_ID = 1
CCBY_ID = 1

class Command(BaseCommand): 
    """
    Pulls data from COS and adds to DB.
    """

    help = "Imports PLOS data from ftps to EA"

    def handle(self, *args, **options):
        print("import plos to EA data")
        if self.check_prereq() == False:
            return
        #self.testEmail()
        

        w = Worker()
        w.processAll()

    def check_prereq(self):
        print("checking prereq")
        if django_settings.IMPORT_TOKEN is None:
            print("add Import token to settings to proceed")
            return False
        if django_settings.REPO_NAME is None or django_settings.CCBY_NAME is None:
            print("add repo and ccby names to settings to proceed")
            return False
        if django_settings.PLOS_SUCCESS is None or django_settings.PLOS_FAILURE is None:
            print("add notification emails to settings to proceed")
            return False
        # get repository
        global REPO_ID
        global PRESS_ID
        global COI_ID
        global DATA_ID
        global CCBY_ID

        # TBD - fix this check
        repo = repository_models.Repository.objects.get(name=django_settings.REPO_NAME)
        REPO_ID = repo.id
        PRESS_ID = repo.press_id
        COI_ID = repository_models.RepositoryField.objects.get_or_create(name='Conflict of interest statement', input_type='text', repository_id = REPO_ID, defaults={'required':0, 'order':1, 'display':0 })[0].id
        DATA_ID = repository_models.RepositoryField.objects.get_or_create(name='Data Availability (Reason not available)', input_type='text', repository_id = REPO_ID, defaults={'required':0, 'order':2, 'display':0 })[0].id
        CCBY_ID = submission_models.Licence.objects.get(name=django_settings.CCBY_NAME,press_id = PRESS_ID).id

        print("REPO_ID" + str(REPO_ID))
        print("PRESS_ID" + str(PRESS_ID))
        print("COI_ID" + str(COI_ID))
        print("DATA_ID" + str(DATA_ID))
        print("CCBY_ID" + str(CCBY_ID))

        return True

    def testEmail(self):
        send_mail(
            'Test Subject',
            'Test message.',
            django_settings.DEFAULT_FROM_EMAIL ,
            django_settings.PLOS_SUCCESS,
            fail_silently=False,
        )


###################
#### Main Worker ##
###################
#############################
class Worker:
    workingDir = '/apps/eschol/import/plos/working'
    doneDir = '/apps/eschol/import/plos/done'
    errorDir = '/apps/eschol/import/plos/error'
    remote = 'ftps.cdlib.org'
    section = 'plos'
    importkey = django_settings.IMPORT_TOKEN
    filesFound = []
    def __init__(self):
        print("created command")
        # get staged files
        self.getStagedFiles()
        # look over the files and process

    def getStagedFiles(self):
        self.filesFound = []
        with FTP_TLS(self.remote, self.section, self.importkey ) as ftps:
            ftps.prot_p()
            print(ftps.nlst())
            # use ftplib to get the files on the server
            self.filesFound = ftps.nlst()
            for filename in self.filesFound:
                local_filename = os.path.join(self.workingDir, filename)
                file = open(local_filename, 'wb')
                ftps.retrbinary('RETR '+ filename, file.write)
                ftps.delete(filename)


    def processAll(self):
        goFiles = list(filter(lambda x: '.go.xml' in x, self.filesFound))
        print(goFiles)
        #find all the go files and 
        for item in goFiles:
            self.processPlosItem(item)

    def processPlosItem(self, gofilename):
        print("processPlosItem")
        print("parse go file for " + gofilename)

        itemIdCreated = None
        goAttribs = None
        preprint = None
        try:
            #get the base name
            goAttribs = self.parseGoFile(gofilename)

            #parse metadata
            article = self.parseMetadata(goAttribs['metadata-filename'], goAttribs['reference-id'])
            print(article)

            
            # create item and related entries
            preprint = PreprintItem(article, self.workingDir, goAttribs['pdf-filename'])
            
            itemIdCreated = preprint.pp.id
            
            print("created item " + str(itemIdCreated) + " for " + gofilename)

            # fill in template and send notification email
            self.sendSuccessEmail(itemIdCreated, goAttribs['reference-id'])
        except Exception as e: 
            print(e)
            traceback.print_exception(*sys.exc_info())
            self.sendFailureEmail("PLOS Import error " + gofilename, str(e))
            # send error email
        finally:
            print("move files")
            self.moveFiles(itemIdCreated, gofilename, goAttribs)


    def parseGoFile(self, gofilename):
        print("gofilename")
        gopath = os.path.join(self.workingDir, gofilename)
        # create element tree object
        tree = ET.parse(gopath)
  
        # get root element
        root = tree.getroot()
        # make sure that root tag is ingest
        assert root.tag == 'ingest', "root tag is expected to be ingest"
        assert root.attrib['type'] == 'eartharxiv', "root type is expected to be eartharxiv"
        # results
        results = {}
        for child in root:
            print(child)
            if child.tag == 'metadata-filename':
                results[child.tag] = child.attrib['name']
            if child.tag == 'pdf-filename':
                results[child.tag] = child.attrib['name']
            if child.tag == 'vendor-id':
                assert child.text == 'plos', "vendor-id text is expected to be plos"
            if child.tag == 'reference-id':
                results['reference-id'] = child.text

        # make sure that go file had the required info and looked right
        assert(results['reference-id'] in results['metadata-filename'])
        assert(results['reference-id'] in results['pdf-filename'])
        return results

    def parseMetadata(self, metafilename, ref):
        print("parse metadata file for " + metafilename)
        metapath = os.path.join(self.workingDir, metafilename)
        # create element tree object
        tree = ET.parse(metapath)
    
        # get root element
        root = tree.getroot()
        assert root.tag == 'article', "root tag is expected to be article"
        print(root.tag)
        jmeta = root.find('front/journal-meta')
        sourceinfo = {}
        sourceinfo['source-item-id'] = ref

        # look at the meta tags and make sure it is as expected
        for child in jmeta:
            print(child)
            if child.attrib['journal-id-type']=="delivering-vendor-id":
                sourceinfo['source-vendor-id'] = child.text
                assert child.text == 'plos', "expecting plos as delivering-vendor-id"
            if child.attrib['journal-id-type']=="delivering-publisher-id":
                sourceinfo['source-publisher-id'] = child.text
                assert child.text == 'PLOS', "expecting PLOS as delivering-publisher-id"
            if child.attrib['journal-id-type']=="delivering-journal-code":
                sourceinfo['source-journal-id'] = child.text               
            if child.attrib['journal-id-type']=="destination-journal-code":
                assert child.text == 'eartharxiv', "expecting eartharxiv as delivering-publisher-id"


        

        return ArticleMetadata(root, sourceinfo)

    def sendSuccessEmail(self, itemId, refId):
        print("send success email " + str(itemId))

        subject = 'EarthArXiv submission success ({0})'.format(refId)
        message = 'At {0}, the manuscript {1} has been successfully submitted to EarthArXiv as Preprint ID {2}.'.format(django.utils.timezone.now(), refId, itemId)
            
        print(message)
        send_mail(
            subject,
            message,
            django_settings.DEFAULT_FROM_EMAIL ,
            django_settings.PLOS_SUCCESS,
            fail_silently=False,
        )

    def sendFailureEmail(self, subject, message):
        print("send failure email " + message)

        send_mail(
            subject,
            message,
            django_settings.DEFAULT_FROM_EMAIL ,
            django_settings.PLOS_FAILURE,
            fail_silently=False,
        )

    def moveFiles(self, itemId, gofilename, goAttribs):
        destFolder = self.errorDir
        if itemId:
            print("move files for " + str(itemId))
            destFolder = self.doneDir
        # if item was created the move to done folder else error folder
        
        if goAttribs:
            moveCmd = "mv {0}* {1}".format(os.path.join(self.workingDir, goAttribs['reference-id']), destFolder)
        else:
            moveCmd = "mv {0}* {1}".format(os.path.join(self.workingDir, gofilename.split('.')[0]), destFolder)
    
        os.system(moveCmd)
    


##############################
class CustomMetadata:
    name = None
    value = None
    def __init__(self, croot):
        print("created custom metadata")
        # parse the metadata 
        self.name = croot.find('meta-name').text
        self.value = croot.find('meta-value').text

##############################
class AuthorMetadata:
    fname = None
    lname = None
    email = None
    orcid = None
    affil = None
    corresp = None
    def __init__(self, contrib):
        print("created author metadata")
        # get name - 
        assert contrib.attrib['contrib-type'] == 'author', "make sure the contributor type"
        if ('corresp' in contrib.attrib):
            self.corresp = contrib.attrib['corresp']
        self.parsename(contrib.find('name'))
        self.parseaddress(contrib.find('address'))
        self.parseid(contrib.find('contrib-id'))

    def parsename(self, namenode):
        print("parse name")
        #make sure name style is western
        assert namenode.attrib['name-style']=="western", "expecting western stye name"
        self.lname = html.unescape(namenode.find('surname').text)
        self.fname = html.unescape(namenode.find('given-names').text)


    def parseaddress(self, addrnode):
        print("parse name")
        self.email = addrnode.find('email').text
        self.affil = addrnode.find('institution').text

    def parseid(self, idnode):
        print("parse id")
        if idnode is not None and 'contrib-id-type' in idnode.attrib and idnode.attrib['contrib-id-type'] == "orcid":
            print("FOUND ORCID")
            self.orcid = idnode.text


##############################
class ArticleMetadata:
    authors = []
    subjects = []
    keywords = []
    customfields = []
    title = None
    abstract = None
    reuse = None
    sourceinfo = None
    def __init__(self, root, sinfo):
        print("created article metadata")
        self.sourceinfo = sinfo
        self.authors = []
        self.subjects = []
        self.keywords = []
        self.customfields = []
        self.fillData(root)
        self.verifyData(root)

    def fillData(self, root):
        print("fill data for article")
        self.title = html.unescape(root.find('front/article-meta/title-group/article-title').text)
        self.abstract = html.unescape(root.find('front/article-meta/abstract/p').text)
        contribsroot = root.find('front/article-meta/contrib-group')
        for child in contribsroot:
            #skip collab authors
            if child.find('collab') is None:
                self.authors.append(AuthorMetadata(child))
        subjsroot = root.find('front/article-meta/article-categories/subj-group')
        if subjsroot is not None:
            for child in subjsroot:
                self.subjects.append(child.text)
        keyroot = root.find('front/article-meta/kwd-group')
        if keyroot is not None:
            for child in keyroot:
                self.keywords.append(child.text)
        customroot = root.find('front/article-meta/custom-meta-group')
        if customroot is not None:
            for child in customroot:
                self.customfields.append(CustomMetadata(child))
        self.reuse = root.find('front/article-meta/permissions/license/license-p').text

    def verifyData(self, root):
        print("verify the data")

        #make sure required custom meta fields are present
        approval = list(filter(lambda x: x.name == "author_approval", self.customfields))[0]
        assert approval.value == 'true', "author approval is expected"
        #make sure cc-by is present
        assert self.reuse == "cc_by", "expecting cc_by"

        #make sure there is atleast one corresponding author 
        owner = list(filter(lambda x: x.corresp == "yes", self.authors))[0]
        assert owner.email != None, "Owner is present"

################################
###### PreprintItem    #########
###### Creates Objects #########
################################
class PreprintItem:
    importedInfo = None
    pdfname = None
    pdfpath = None
    pp = None
    dateCreated = None
    def __init__(self, article, path, pdfname):
        print("do all the work")
        self.importedInfo = article
        self.pdfname = pdfname
        self.pdfpath = os.path.join(path, pdfname)
        self.dateCreated = django.utils.timezone.now()
        self.createItem()


    def createItem(self):
        print("create the item")
        # let's make sure there is not other item with this source item id
        # TBD
        # create item
        self.pp = repository_models.Preprint.objects.create(title = self.importedInfo.title, abstract = self.importedInfo.abstract, stage='preprint_unsubmitted', current_step=5,
                                                                                        preprint_decision_notification = 0, repository_id = REPO_ID, 
                                                                                        license_id = CCBY_ID, date_started = self.dateCreated, date_submitted = self.dateCreated)

        print("CREATED PPRINT " + str(self.pp.id))
        # save file
        self.addfile()

        # find the subject
        self.addSubjects()
        self.addKeywords()

        # create user if needed
        self.addAuthors()
        # create author if needed

        self.addFields()
        self.addDatalinks()
        self.pp.stage = 'preprint_review'
        self.pp.save()

    def addfile(self):
        print("add submission file")
        # copy file from working folder to the dest folder
        repoPath = os.path.join('repos', str(self.pp.id), self.pdfname)
        basePath = os.path.join(django_settings.BASE_DIR, 'files','repos', str(self.pp.id))
        file_size = os.path.getsize(self.pdfpath)
        if not os.path.exists(basePath):
            os.makedirs(basePath)
        # copy the file
        copyCmd = "cp {0} {1}".format(self.pdfpath, os.path.join(basePath, self.pdfname))
        print(copyCmd)
        os.system(copyCmd)

        
        pf = repository_models.PreprintFile.objects.create(file=repoPath, original_filename = self.pdfname,uploaded = self.dateCreated, 
                                                                                        mime_type='application/pdf', size = file_size, preprint_id = self.pp.id)
        self.pp.submission_file_id = pf.id    
        #self.pv = repository_models.PreprintVersion.objects.get_or_create(file_id=self.pf.id, preprint_id=pp.id, defaults={'version':self.osfId, 'date_time': self.dateCreated})[0]


        

    def addSubjects(self):
        # parse the subject tag
        print("add subject")
        for subject in self.importedInfo.subjects:
            parts = subject.split(':')
            print(parts[0].strip())
            print(parts[1].strip())
            parentId = repository_models.Subject.objects.get(name=parts[0].strip(), repository_id=REPO_ID, parent_id=None).id
            subjectObj = repository_models.Subject.objects.get(name=parts[1].strip(), repository_id=REPO_ID, parent_id=parentId)
            self.pp.subject.add(subjectObj)


    def addKeywords(self):
        print("add keywords")
        for keyword in self.importedInfo.keywords:
            parts = keyword.split(',')
            for part in parts:
                print(part)
                result = submission_models.Keyword.objects.get_or_create(word=part)[0]
                self.pp.keywords.add(result)



    def addAuthors(self):
        print("add author")
        print("creating account for the author")
        order = 0
        for auth in self.importedInfo.authors:
            order += 1
            # process all authors and return id of the corresponding one
            result_auth = repository_models.Author.objects.get_or_create(email_address=auth.email, defaults={'first_name':auth.fname, 'last_name': auth.lname, 'orcid':auth.orcid, 'affiliation':auth.affil})[0]

            result_acc = core_models.Account.objects.get_or_create(email=auth.email, username=auth.email, defaults={'password':uuid4(), 'is_superuser': 0, 
                                                                                                        'first_name':auth.fname, 'last_name':auth.lname, 'orcid':auth.orcid,
                                                                                                        'institution':auth.affil, 'is_active':0, 'is_staff':0, 'is_admin':0, 
                                                                                                        'enable_digest':0, 'enable_public_profile':0, 
                                                                                                        'date_joined': self.dateCreated, 'uuid':uuid4()})[0]
            repository_models.PreprintAuthor.objects.get_or_create(preprint_id=self.pp.id, account_id = result_acc.id, defaults={'order': order, 'affiliation':auth.affil})
            if auth.corresp == "yes":
                self.pp.owner_id = result_acc.id

    def addFields(self):
        print("add fields")
        self.pp.comments_editor = 'This is a PLOS->EarthArXiv submission: {0}; {1}'.format(self.importedInfo.sourceinfo['source-item-id'], self.importedInfo.sourceinfo['source-journal-id'])
        #self.pp.comments_editor = "{0} item referenced {1} from journal {2}".format(self.importedInfo.sourceinfo['source-publisher-id'], self.importedInfo.sourceinfo['source-item-id'], self.importedInfo.sourceinfo['source-journal-id'])
        for field in self.importedInfo.customfields:
            if field.name == "coi_stmt":
                print("Adding confict of interest " + field.value)
                repository_models.RepositoryFieldAnswer.objects.get_or_create(preprint_id=self.pp.id, field_id = COI_ID, defaults={'answer': field.value})
            if field.name == "data_availability":
                print("Adding data availability " + field.value)
                repository_models.RepositoryFieldAnswer.objects.get_or_create(preprint_id=self.pp.id, field_id = DATA_ID, defaults={'answer': field.value})

    def addDatalinks(self):
        print("add data link")
        num = 1
        for field in self.importedInfo.customfields:
            if field.name == "data_availability_link":
                print("Adding data link " + field.value)
                repository_models.PreprintSupplementaryFile.objects.get_or_create(preprint_id=self.pp.id, url = field.value, defaults={'label':'Public data', 'order':num})
                num += 1



