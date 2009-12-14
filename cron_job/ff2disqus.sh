#!/bin/bash
echo `date '+%m/%d/%Y %H:%M:%S'` "] Starting FF2Disqus Batch Process"
for s in $(/usr/local/bin/curl -s -f https://ff2disqus.appspot.com/get_users | /usr/local/bin/gsed 's/,/ /g'); do 
   echo "Processing ff_user=$s"
   /usr/local/bin/curl -s --retry 5 https://ff2disqus.appspot.com/sync_comments?ff_user=$s
  echo ""
done

