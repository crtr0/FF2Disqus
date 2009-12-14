#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
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
#

import wsgiref.handlers
import friendfeed
import logging
import datetime
import sys
import re

#from django.utils.encoding import smart_str, smart_unicode
from urllib import urlencode
from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.runtime import DeadlineExceededError
from google.appengine.api import mail

from django.utils import simplejson
from django.utils.html import strip_tags

class User(db.Model):
  ff_user = db.StringProperty(required=True)
  ff_key = db.StringProperty()
  ff_service = db.StringProperty(required=True)  
  d_forum_key = db.StringProperty(required=True)
  sync_mode = db.IntegerProperty(required=True)
  sync_messages = db.StringListProperty()
  last_sync = db.DateTimeProperty()

class TestHandler(webapp.RequestHandler):

  def get(self):
    self.response.out.write("test")
  
class DisqusHandler(webapp.RequestHandler):

  def get(self):
    args = {}
    for arg in self.request.arguments():
      if arg != 'method':
        args[arg] = self.request.get(arg)
    method = self.request.get('method')
    url = 'http://disqus.com/api'+self.request.get('method')+'?'+urlencode(args)
    self.response.out.write(urlfetch.fetch(url, payload={}, method=urlfetch.GET, headers={}).content)

class FFHandler(webapp.RequestHandler):

  def get(self):
    out = {}
    ff_user = self.request.get('ff_user')
    ff_key = self.request.get('ff_remotekey')
    
    ff_api = friendfeed.FriendFeed(ff_user, ff_key)
    ff_profile = ff_api.fetch_user_profile(ff_user)
    if ff_profile.has_key('errorCode'):
       out['success'] = False
       out['message'] = 'FriendFeed key did not validate'
    else:
       out['success'] = True
       out['message'] = 'Successfully got profile for '+ff_user
       out['services'] = [s for s in ff_profile['services'] if s['id'] == 'blog' or s['id'] == 'tumblr' or s['id'] == 'feed']
       
    self.response.out.write(simplejson.dumps(out))

class UserHandler(webapp.RequestHandler):

  def get(self):
    d_forum_key = self.request.get('d_forum_key')
    ff_user = self.request.get('ff_user')
    ff_key = self.request.get('ff_remotekey')
    ff_service = self.request.get('ff_service')
    sync_mode = int(self.request.get('sync_mode'))
    sync_messages = []
    out = {}
    
    try:    
       user = User.get_by_key_name('ff_'+ff_user)
       if sync_mode == 0:
         if user is not None:
           user.delete()
           out['message'] = 'Your account has been deleted'
       else:
         if user is None:
           user = User(key_name='ff_'+ff_user,ff_user=ff_user,ff_key=ff_key,d_forum_key=d_forum_key,sync_mode=sync_mode,ff_service=ff_service)
         else:
           user.d_forum_key = d_forum_key
           user.ff_user = ff_user
           user.ff_key = ff_key
           user.ff_service = ff_service
           user.sync_mode = sync_mode
         user.put()
         sync_messages = user.sync_messages[-20:]
         out['message'] = 'success'
         out['log'] = sync_messages
    except:
      logging.error(sys.exc_info())
      out['message'] = 'Unknown Error (check form, keys, etc)'
      
    self.response.out.write(simplejson.dumps(out))

class GetUsersHandler(webapp.RequestHandler):

  def get(self):
    results = [u.ff_user for u in User.all().filter('sync_mode >', 0)]
    self.response.out.write(",".join(results))

class SyncCommentsHandler(webapp.RequestHandler):

  def get(self):
    #self.error(500)
    #self.response.out.write(simplejson.dumps({'success':False, 'errorCode': 'service-down', 'message':'This service is current down'}))
    #return
    
    url_shorteners = ['is.gd', 'tinyurl.com', 'bit.ly', 'snurl.com']
    url_pattern = re.compile('http://[\w\.]+/\w+')
    
    messages = []
    try:
      ff_user = self.request.get('ff_user')
      user = User.get_by_key_name('ff_'+ff_user)
      if user is not None and user.sync_mode > 0:
         ff_api = friendfeed.FriendFeed(ff_user, user.ff_key)
         
         #ff_feed = ff_api.fetch_user_feed(ff_user, service=user.ff_service)
         ff_feed = ff_api.fetch_user_feed(ff_user)
         
         # loop through most recent entries (for a particular service)
         for e in ff_feed['entries']:
           # if there are comments on FF
           if (e['service']['id'] == user.ff_service or e['service']['id'] == 'twitter') and len(e['comments']) > 0:
             if (user.last_sync is None or e['comments'][-1]['date'] > user.last_sync):
               
               # here is where I might look for shortened-urls and see about expanding them.
               if e['service']['id'] == 'twitter':
                 # looks for links
                 matches = url_pattern.findall(e['title'])
                 if len(matches) == 1:
                   e['link'] = matches[0]
                   if len(filter(lambda x: e['link'].find(x) != -1, url_shorteners)) > 0:
                     # enlarge the link      
                     try:
                       e['link'] = urlfetch.fetch(e['link'], payload={}, method=urlfetch.HEAD, headers={},follow_redirects=False).headers['location']
                     except:
                       logging.debug('Error trying to expand url='+e['link'])
                       logging.error(sys.exc_info()) 
               
               url = 'http://disqus.com/api/get_thread_by_url/?'+urlencode({'forum_api_key':user.d_forum_key,'url':e['link']})
               d_thread = simplejson.loads(urlfetch.fetch(url, payload={}, method=urlfetch.GET, headers={}).content)
               # if we have found a corresponding thread on Disqus
               if d_thread['succeeded'] and d_thread['message'] is not None:
                 # start looping through the ff comments that are new as of the last sync
                 new_ff_comments = [c for c in e['comments'] if user.last_sync is None or c['date'] > user.last_sync]
                 for ff_c in new_ff_comments:
                   syncd = False

                   # if the thread has existing comments, pull them back
                   if d_thread['message']['num_comments'] > 0:
                     url = 'http://disqus.com/api/get_thread_posts/?'+urlencode({'forum_api_key':user.d_forum_key,'thread_id':d_thread['message']['id']})
                     content = urlfetch.fetch(url, payload={}, method=urlfetch.GET, headers={}).content               
                     all_comments = simplejson.loads(content)['message']
                     d_thread['comments'] = filter(lambda x:x['shown'], all_comments)
                     # compare every FF comment to every D comment, and mark the FF comments that have already been syncd
                     for d_c in d_thread['comments']:
                       if re.sub("\W", "", ff_c['body']).find(re.sub("\W", "", strip_tags(d_c['message'])[0:400])) != -1  or re.sub("\W", "", ff_c['body']) == re.sub("\W", "", d_c['message']):
                         #ff_c['syncd'] = True
                         syncd = True

                   if not syncd:
                     url = 'http://disqus.com/api/create_post/'
                     disqus_date = ff_c['date'].strftime('%Y-%m-%dT%H:%M')
                     post_data = {'forum_api_key': user.d_forum_key, 'thread_id': d_thread['message']['id'], 'message': ff_c['body'], 'author_name': ff_c['user']['name'], 'author_email': ff_c['user']['nickname']+'@bogus_email.com', 'author_url': ff_c['user']['profileUrl'], 'created_at': disqus_date}
                     encoded_post = urlencode(dict([(k, unicode(v).encode('utf-8')) for k, v in post_data.items()]))
                     resp = urlfetch.fetch(url, payload=encoded_post, method=urlfetch.POST, headers={}).content
                     try:
                       resp = simplejson.loads(resp)
                       if resp['succeeded']:
                         messages.append('['+str(datetime.datetime.now())+'] Copied comment to Disqus: "'+re.sub("(\s)+", " ", ff_c['body'])[0:100]+'..."')
                     except:
                       logging.debug('['+str(datetime.datetime.now())+'] FAILED to copy comment to Disqus: "'+re.sub("(\s)+", " ", ff_c['body'])[0:100]+'..."')


               # technically, this check is no longer needed...
               #if user.sync_mode == 1 or user.sync_mode == 3:
               #  for ff_c in e['comments']:
               #    if not ff_c.has_key('syncd'):
               #      url = 'http://disqus.com/api/create_post/'
               #      disqus_date = ff_c['date'].strftime('%Y-%m-%dT%H:%M')
               #      
               #      post_data = {'forum_api_key': user.d_forum_key, 'thread_id': d_thread['message']['id'], 'message': ff_c['body'], 'author_name': ff_c['user']['name'], 'author_email': ff_c['user']['nickname']+'@bogus_email.com', 'author_url': ff_c['user']['profileUrl'], 'created_at': disqus_date}
               #      encoded_post = urlencode(dict([(k, unicode(v).encode('utf-8')) for k, v in post_data.items()]))
               #      resp = urlfetch.fetch(url, payload=encoded_post, method=urlfetch.POST, headers={}).content
               #      
               #      try:
               #        resp = simplejson.loads(resp)
               #        if resp['succeeded']:
               #           messages.append('['+str(datetime.datetime.now())+'] Copied comment to Disqus: "'+re.sub("(\s)+", " ", ff_c['body'])[0:100]+'..."')
               #      except:
               #        logging.debug('['+str(datetime.datetime.now())+'] FAILED to copy comment to Disqus: "'+re.sub("(\s)+", " ", ff_c['body'])[0:100]+'..."')
           
             #if user.sync_mode == 2 or user.sync_mode == 3:
             #  if len(d_thread['comments']) > 0:
             #    for d_c in d_thread['comments']:
             #      if not d_c.has_key('syncd'):
             #        #logging.info('XXXX'+re.sub("\s", "", strip_tags(d_c['message']))[0:800])
             #        #logging.info(d_c['message'])
             #        body = strip_tags(d_c['message'])                  
             #        if len(body) > 800:
             #           body = body[0:800]+'...'
             #        body += ' (comment via Disqus by ' 
             #        if d_c['is_anonymous']:
             #          body += d_c['anonymous_author']['name']
             #        else:
             #          body += d_c['author']['display_name'] if d_c['author']['display_name'] != '' else d_c['author']['username']
             #        body += ')'
             #        try:
             #          new_comment = ff_api.add_comment(e['id'], body)
             #          if new_comment.has_key('id'):
             #            messages.append('['+str(datetime.datetime.now())+'] Copied comment to FF: "'+re.sub("(\s)+", " ", strip_tags(d_c['message']))[0:100]+'..."')
             #          else:
             #            logging.error('Failed to post comment to FF: '+new_comment['errorCode'])
             #        except:
             #          logging.warn('['+str(datetime.datetime.now())+'] FAILED to copy comment to FF: "'+re.sub("(\s)+", " ", strip_tags(d_c['message']))[0:100]+'..."')             
             
         user.sync_messages.extend(messages)
         user.last_sync = datetime.datetime.now()
         user.put()
         self.response.out.write(simplejson.dumps({'success':True, 'message': messages}))
      else:
         self.error(500)
         self.response.out.write(simplejson.dumps({'success':False, 'errorCode': 'invalid-user', 'message':'User does not exist or has syncing turned-off'}))
      
    except DeadlineExceededError:
      user.last_sync = datetime.datetime.now()
      user.put()
      self.error(500)   
      self.response.out.write(simplejson.dumps({'success':False, 'errorCode': 'time-out', 'message':'Google AppEngine has timed-out (too many comments to sync). Your next sync will only fetch new comments (starting now).'}))

    except:
      logging.error(sys.exc_info()) 
      self.error(500)   
      self.response.out.write(simplejson.dumps({'success':False, 'errorCode': 'unknown-error', 'message':'An unknown error has occurred'}))
    

def main():
  application = webapp.WSGIApplication([
    ('/test', TestHandler),
    ('/user', UserHandler),
    ('/disqus', DisqusHandler),
    ('/ff', FFHandler),
    ('/get_users', GetUsersHandler),
    ('/sync_comments', SyncCommentsHandler)
    ], debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
