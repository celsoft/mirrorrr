#!/usr/bin/env python
# Copyright 2008-2014 Brett Slatkin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__author__ = "Brett Slatkin (bslatkin@gmail.com)"

import datetime
import hashlib
import logging
import re
import time
import urllib
import wsgiref.handlers

from google.appengine.api import memcache
from google.appengine.api import urlfetch
import webapp2
from google.appengine.ext.webapp import template
from google.appengine.runtime import apiproxy_errors

import transform_content

###############################################################################

DEBUG = False
EXPIRATION_DELTA_SECONDS = 3600

# DEBUG = True
# EXPIRATION_DELTA_SECONDS = 10

HTTPS_PREFIX = "https://"

IGNORE_HEADERS = frozenset([
  "set-cookie",
  "expires",
  "cache-control",

  # Ignore hop-by-hop headers
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
])

TRANSFORMED_CONTENT_TYPES = frozenset([
  "text/html",
  "text/css",
])

MAX_CONTENT_SIZE = 10 ** 6 - 600

###############################################################################

class MirroredContent(object):
  def __init__(self, original_address, translated_address,
               status, headers, data, base_url):
    self.original_address = original_address
    self.translated_address = translated_address
    self.status = status
    self.headers = headers
    self.data = data
    self.base_url = base_url

  @staticmethod
  def fetch_and_store(base_url, translated_address, mirrored_url):
    """Fetch and cache a page.

    Args:
      base_url: The hostname of the page that's being mirrored.
      translated_address: The URL of the mirrored page on this site.
      mirrored_url: The URL of the original page. Hostname should match
        the base_url.

    Returns:
      A new MirroredContent object, if the page was successfully retrieved.
      None if any errors occurred or the content could not be retrieved.
    """

    #logging.info('Base_url = "%s", mirrored_url = "%s"', base_url, mirrored_url)

    #logging.info("Fetching '%s'", mirrored_url)
    try:
      response = urlfetch.fetch(mirrored_url)
    except (urlfetch.Error, apiproxy_errors.Error):
      logging.info("Could not fetch URL")
      return None

    adjusted_headers = {}
    for key, value in response.headers.iteritems():
      adjusted_key = key.lower()
      if adjusted_key not in IGNORE_HEADERS:
        adjusted_headers[adjusted_key] = value

    content = response.content
    #logging.info("content '%s'", content)
    page_content_type = adjusted_headers.get("content-type", "")
    for content_type in TRANSFORMED_CONTENT_TYPES:
      # startswith() because there could be a 'charset=UTF-8' in the header.
      if page_content_type.startswith(content_type):
        content = transform_content.TransformContent(base_url, mirrored_url, content)
        break

    new_content = MirroredContent(
      base_url=base_url,
      original_address=mirrored_url,
      translated_address=translated_address,
      status=response.status_code,
      headers=adjusted_headers,
      data=content)

    return new_content

###############################################################################

class WarmupHandler(webapp2.RequestHandler):
  def get(self):
    pass

class BaseHandler(webapp2.RequestHandler):
  def get_relative_url(self):
    slash = self.request.url.find("/", len(self.request.scheme + "://"))
    if slash == -1:
      return "/"
    return self.request.url[slash:]
  def is_recursive_request(self):
    if "AppEngine-Google" in self.request.headers.get("User-Agent", ""):
      logging.warning("Ignoring recursive request by user-agent=%r; ignoring")
      self.error(404)
      return True
    return False

class MirrorHandler(BaseHandler):
  def get(self, base_url):

    if self.is_recursive_request():
      return

    base_url = 'joycasino-sayt-oficialniy.com'

    # Log the user-agent and referrer, to see who is linking to us.
    #logging.info('User-Agent = "%s", Referrer = "%s"', self.request.user_agent, self.request.referer)
    #logging.info('Base_url = "%s", url = "%s"', base_url, self.request.url)

    translated_address = self.get_relative_url()  # remove leading /
    logging.info("translated_address '%s'", translated_address)
    mirrored_url = HTTPS_PREFIX + base_url + translated_address

    #logging.info("Handling request for '%s'", mirrored_url)

    content = MirroredContent.fetch_and_store(base_url,
                                                translated_address,
                                                mirrored_url)
                                                
    if content is None:
      return self.error(404)

    for key, value in content.headers.iteritems():
      self.response.headers[key] = value
    if not DEBUG:
      self.response.headers["cache-control"] = \
        "max-age=%d" % EXPIRATION_DELTA_SECONDS

    self.response.out.write(content.data)

class HomeHandler(BaseHandler):
  def get(self):

    if self.is_recursive_request():
      return

    form_url = HTTPS_PREFIX + 'joycasino-sayt-oficialniy.com'
    if form_url:
      # Accept URLs that still have a leading 'http://'
      inputted_url = urllib.unquote(form_url)
      logging.info("inputted_url '%s'", inputted_url)

      content = MirroredContent.fetch_and_store(form_url, form_url, form_url)

      if content is None:
        return self.error(404)

      for key, value in content.headers.iteritems():
        self.response.headers[key] = value
      if not DEBUG:
        self.response.headers["cache-control"] = \
          "max-age=%d" % EXPIRATION_DELTA_SECONDS

      self.response.out.write(content.data)

###############################################################################

app = webapp2.WSGIApplication([
  (r"/", HomeHandler),
  (r"/([^/]+).*", MirrorHandler),
  (r"/_ah/warmup", WarmupHandler),
], debug=DEBUG)
