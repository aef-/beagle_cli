import requests
import sys, os
import json

class AccessBeagleEndpoint:
  def __init__(self):
    username = os.environ['DEREGISTER_USER']
    password = os.environ['DEREGISTER_PW']
    BEAGLE_ENDPOINT = os.environ['BEAGLE_ENDPOINT']
    self.auth = requests.auth.HTTPBasicAuth(username, password)
    self.API = BEAGLE_ENDPOINT

  def run_url(self, url):
    """
    Runs the url, which should contain all the parameters we'd need
    """
    req = requests.get(url, auth=self.auth, verify=False)
    return req.json()

  # had to build url weird because the requests docs were busted and I kept running into issues
  def get_run_request(self, request_id):
    url =  "%s/v0/etl/jobs/?page_size=1000&request_id=%s" % (self.API, request_id)
    return self.run_url(url)


  def get_run(self, run_id):
    url =  "%s/v0/etl/jobs/%s" % (self.API, run_id)
    return self.run_url(url)


  def get_file_ids(self, request_id):
    url =  "%s/v0/fs/files/?page_size=1000&metadata=requestId:%s" % (self.API, request_id)   
    data = self.run_url(url)
    file_ids = list()
    for result in data['results']:
      file_ids.append(result['id'])
    return file_ids
