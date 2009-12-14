function callApi(url, method, params, callback) {
    new Ajax.Request(url, {
       async: 'async',
       method: method,
       parameters: params,
       onComplete: function(transport) {
          //alert(transport.responseText);
          callback(transport.responseText.evalJSON(true));
       }
     });
}

function savedUser(response) {
  if (response.message == 'success') {
     alert('Information Saved!');
     $('ping_url').writeAttribute('href', 'https://ff2disqus.appspot.com/sync_comments?ff_user='+$F('ff_nickname'));
     $('message').show();
     $('log_header').show();
     $('log').update("");
     response.log.reverse().each(function(m) {
        $('log').insert(m+'<br/>');
     });
  }
  else {
    alert(response.message);
    $('message').hide();
    $('log_header').hide();
    $('log').hide();    
  }
}

function saveUser() {
  if (!$F('d_forum_key').blank() && !$F('ff_nickname').blank() && !$F('ff_service').blank()) {
    callApi('/user',
          'get',
          {d_forum_key: $F('d_forum_key'), ff_user: $F('ff_nickname'),sync_mode: $F('sync_mode'), ff_service: $F('ff_service')},
          savedUser);
  }
  else {
    alert('You must fill-in all values and drop-downs');
  }
}

function gotFF(response) {
  if (response.success) {
     response.services.each(function(s) {
        if (s.profileUrl != null) {
           try { $('ff_service').add(new Option(s.profileUrl, s.id), null); }
           catch(e) {$('ff_service').add(new Option(s.profileUrl, s.id)); }
        }
     });
     $('ff_service').writeAttribute('selectedIndex', 0);
     $('save_button').enable();  
  }
  else {
    alert(response.message);
  }
}

function ff() {
  callApi('/ff',
          'get',
          {ff_user: $F('ff_nickname')},
          gotFF);
}


function gotForumApiKey(response) {
  if (response.succeeded) { 
     $('d_forum_key').writeAttribute('value', response.message);
     $('ff_button').enable();  
     $('save_button').enable();  
  }
  else {
     alert(response.message);
     $('save_button').disable();  
  }
}

function getForumApiKey() {
  forum_id = $F('disqus_forum_list');
  callApi('/disqus',
          'get',
          {method: '/get_forum_api_key/', user_api_key: $F('disqus_api_key'),forum_id: forum_id},
          gotForumApiKey);
}

function gotForumList(response) {
  if (response.succeeded) {
     response.message.each(function(forum) {
        try { $('disqus_forum_list').add(new Option(forum.name, forum.id), null); }
        catch(e) {$('disqus_forum_list').add(new Option(forum.name, forum.id)); }
     });
  }
  else {
    alert(response.message);
  }
}

function disqus() {
  callApi('/disqus',
          'get',
          {method: '/get_forum_list/', user_api_key: $F('disqus_api_key')},
          gotForumList);
}

function toggle() {
   $('log').toggle();
   $('log_link').update( ($('log').visible() ? '(hide)' : '(show)') ); 
}