#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#
# Copyright (C) Martijn Voncken 2008 <mvoncken@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, write to:
#     The Free Software Foundation, Inc.,
#     51 Franklin Street, Fifth Floor
#     Boston, MA  02110-1301, USA.
#
#  In addition, as a special exception, the copyright holders give
#  permission to link the code of portions of this program with the OpenSSL
#  library.
#  You must obey the GNU General Public License in all respects for all of
#  the code used other than OpenSSL. If you modify file(s) with this
#  exception, you may extend this exception to your version of the file(s),
#  but you are not obligated to do so. If you do not wish to do so, delete
#  this exception statement from your version. If you delete this exception
#  statement from all source files in the program, then also delete it here.
#


#todo: remove useless imports.

from utils import *
import utils #todo remove the line above.
from render import render, error_page
import page_decorators as deco

from deluge.common import get_pixmap
from deluge.log import LOG as log

import web
from web import url
from lib.static_handler import static_handler

from operator import attrgetter
import os
from deluge import component
from deluge.ui.client import sclient as proxy
from deluge.configmanager import ConfigManager

page_manager = component.get("PageManager")
config = ConfigManager("webui06.conf")

def route(url, klass):
    """
    url-mapping is using page_manager
    not the default web.py way ; I want class decorators!
    """
    page_manager.register_page(url, klass)

#pages:
class login:
    @deco.deluge_page_noauth
    def GET(self, name):
        vars = web.input(error = None)
        return render.login(vars.error)

    def POST(self):
        vars = web.input(pwd = None, redir = None)

        if utils.check_pwd(vars.pwd):
            #start new session
            start_session()
            utils.seeother('/index')
        elif vars.redir:
            utils.seeother(url('/login', error=1, redir=vars.redir))
        else:
            utils.seeother('/login?error=1')

route('/login',login)

class index:
    "page containing the torrent list."
    @deco.deluge_page
    @deco.auto_refreshed
    def GET(self, name):
        vars = web.input(sort=None, order=None, filter_cat=None ,filter_value=None , tracker=None)

        #cookies are a delicious delecacy.
        if not vars.sort: #no arguments, default to coockies.
            newvars = cookies()
            if vars.filter_cat: #i'm doing it wrong :( , but it works..
                newvars['filter_cat'] = vars.filter_cat
                newvars['filter_value'] = vars.filter_value
            vars.update(newvars)


        else: #has arguments:set cookies from arguments.
            for key in ["sort", "order", "filter_cat","filter_value"]:
                value = getattr(vars, key) or ""
                setcookie(key, value)

        #organize-filters
        label_filters = {}
        if 'label' in [pl.lower() for pl in proxy.get_enabled_plugins()]:
            filter_dict = {}
            if vars.filter_cat and vars.filter_value and vars.filter_value <> "All":
                filter_dict = {vars.filter_cat:vars.filter_value}

            torrent_ids =  proxy.label_get_filtered_ids(filter_dict)
            label_filters = proxy.label_filter_items()

        else:
            torrent_ids =  proxy.get_session_state()

        torrent_list = utils.get_enhanced_torrent_list(torrent_ids)

        #sorting:
        if vars.sort:
            try:
                torrent_list.sort(key=attrgetter(vars.sort))
            except:
                log.error('Sorting Failed')

            if vars.order == 'up':
                torrent_list = list(reversed(torrent_list))

        return render.index(torrent_list, label_filters)
route('/index',index)

#simple proxy's to deluge.ui.client
#execute a command on torrent(s) and redirect to index page.
def reg_torrents_POST(url_name, proxy_command):
    class _page_class:
        @deco.check_session
        @deco.torrent_ids
        def POST(self, torrent_ids):
            getattr(proxy, proxy_command)(torrent_ids)
            do_redirect()
    _page_class.__name__ = "TORRENTS_POST:" + proxy_command
    route("/torrent/%s/(.*)" % url_name, _page_class)

reg_torrents_POST("start", "resume_torrent")
reg_torrents_POST("stop", "pause_torrent")
reg_torrents_POST("recheck", "force_recheck")
reg_torrents_POST("reannounce", "force_reannounce")
reg_torrents_POST("queue/up", "queue_up")
reg_torrents_POST("queue/down", "queue_down")
reg_torrents_POST("queue/top", "queue_top")
reg_torrents_POST("queue/bottom", "queue_bottom")


class torrent_info:
    @deco.deluge_page
    @deco.auto_refreshed
    @deco.torrent
    def GET(self, torrent):
        return render.torrent_info(torrent)
route("/torrent/info/(.*)", torrent_info)

class torrent_info_inner:
    @deco.deluge_page
    @deco.torrent
    def GET(self, torrent):
        vars = web.input(tab = None)
        if vars.tab:
            active_tab = vars.tab
        else:
            active_tab =  getcookie("torrent_info_tab") or "details"
        setcookie("torrent_info_tab", active_tab)
        return render.torrent_info_inner(torrent, active_tab)
route("/torrent/info_inner/(.*)", torrent_info_inner)

class torrent_delete:
    @deco.deluge_page
    @deco.torrent_list
    def GET(self, torrent_list):
            torrent_str = ",".join([t.id for t in torrent_list])
            #todo: remove the ",".join!
            return render.torrent_delete(torrent_str, torrent_list)

    @deco.check_session
    @deco.torrent_ids
    def POST(self, torrent_ids):
        vars = web.input(data_also = None, torrent_also = None)
        data_also = bool(vars.data_also)
        torrent_also = bool(vars.torrent_also)
        proxy.remove_torrent(torrent_ids, torrent_also, data_also)
        do_redirect()
route("/torrent/delete/(.*)",torrent_delete)

class torrent_files:
    @deco.deluge_page
    @deco.torrent
    def GET(self,torrent):
        return render.torrent_files(torrent, None)

    @deco.check_session
    @deco.torrent
    def POST(self, torrent):
        values = web.input()
        file_priorities = []
        for i in xrange(len(torrent.files)):
            file_priorities.append(int(getattr(values,"prio_%s" % i )))

        proxy.set_torrent_file_priorities(torrent.id, file_priorities)
        do_redirect()
route("/torrent/files/(.*)", torrent_files)

class torrent_trackers:
    @deco.check_session
    @deco.torrent
    def POST(self, torrent):
        vars = web.input(tier=[], url=[])

        tiers_int = [int(t) for t in vars.tier]
        sorted_urls =  [url for num,url in sorted(zip(tiers_int, vars.url)) if url]
        trackers = [{'tier':i , 'url':url} for i,url in enumerate(sorted_urls)]

        proxy.set_torrent_trackers(torrent.id, trackers)
        do_redirect()
route("/torrent/trackers/(.*)", torrent_trackers)

class pause_all:
    @deco.check_session
    def POST(self, name):
        proxy.pause_torrent(proxy.get_session_state())
        do_redirect()
route("/pause_all", pause_all)

class resume_all:
    @deco.check_session
    def POST(self, name):
        proxy.resume_torrent(proxy.get_session_state())
        do_redirect()
route("/resume_all", resume_all)

class refresh:
    def GET(self, name):
        return self.POST(name)
        #WRONG, but makes it easyer to link with <a href> in the status-bar

    @deco.check_session
    def POST(self, name):
        auto_refresh = {'off': '0', 'on': '1'}[name]
        setcookie('auto_refresh', auto_refresh)
        if not getcookie('auto_refresh_secs'):
            setcookie('auto_refresh_secs', 10)
        do_redirect()
route("/refresh/(.*)", refresh)

class refresh_set:
    @deco.deluge_page
    def GET(self, name):
        return render.refresh_form()

    @deco.check_session
    def POST(self, name):
        vars = web.input(refresh = 0)
        refresh = int(vars.refresh)
        if refresh > 0:
            setcookie('auto_refresh', '1')
            setcookie('auto_refresh_secs', str(refresh))
            do_redirect()
        else:
            error_page(_('refresh must be > 0'))
route("/refresh/set", refresh_set)

class home:
    @deco.check_session
    def GET(self, name):
        do_redirect()
route('/home', home)
route('/', home)

class about:
    @deco.deluge_page_noauth
    def GET(self, name):
        return render.about()
route('/about', about)

class logout:
    def GET(self):
        return self.POST()
        #WRONG, but makes it easyer to link with <a href> in the status-bar
    @deco.check_session
    def POST(self, name):
        end_session()
        utils.seeother('/login')
route('/logout', logout)

class connect:
    @deco.check_session
    @deco.deluge_page_noauth
    def GET(self, name):
        restart = False
        try:
            proxy.ping()
            connected = proxy.get_core_uri()
            if connected.startswith("http://localhost"):
                restart = True
        except:
            connected = None

        connect_list = ["http://localhost:58846"]
        if config.get('daemon') <> "http://localhost:58846":
            connect_list = [config.get('daemon')] + connect_list

        return render.connect(connect_list, connected ,restart)

    def POST(self):
        vars = web.input(uri = None, other_uri = None)
        uri = ''
        print "URI=",uri
        if vars.uri == 'other':
            if not vars.other_uri:
                return error_page(_("no uri"))
            uri = vars.other_uri
        else:
            uri = vars.uri
        #TODO: more error-handling
        utils.daemon_connect(uri)
        do_redirect()
route('/connect', connect)

class daemon_control:
    @deco.check_session
    def POST(self, command):
        if command == 'stop':
            proxy.shutdown()
        elif command == 'start':
            self.start()
            return do_redirect()
        elif command == 'restart':
            proxy.shutdown()
            self.start()
            return do_redirect()
        else:
            raise Exception('Unknown command:"%s"' % command)

        utils.seeother('/connect')

    def start(self):
        import time
        uri = web.input(uri = None).uri
        if not uri:
            uri = 'http://localhost:58846'
        port = int(uri.split(':')[2])
        utils.daemon_start_localhost(port)
        time.sleep(1)  #pause a while to let it start?
        utils.daemon_connect( uri )
route("/daemon/control/(.*)", daemon_control)

#other stuff:
class remote_torrent_add:
    """
    For use in remote scripts etc.
    curl ->POST pwd and torrent as file
    greasemonkey: POST pwd torrent_name and data_b64
    """
    @deco.remote
    def POST(self, name):
        vars = web.input(pwd = None, torrent = {},
            data_b64 = None , torrent_name= None)

        if not utils.check_pwd(vars.pwd):
            return 'error:wrong password'

        if vars.data_b64: #b64 post (greasemonkey)
            data_b64 = unicode(vars.data_b64)
            torrent_name = vars.torrent_name
        else:  #file-post (curl)
            data_b64 = base64.b64encode(vars.torrent.file.read())
            torrent_name = vars.torrent.filename
        proxy.add_torrent_filecontent(torrent_name, data_b64)
        return 'ok'
route("/remote/torrent/add(.*)", remote_torrent_add)

class static(static_handler):
    base_dir = os.path.join(os.path.dirname(__file__), 'static')
route("/static/(.*)", static)

class template_static(static_handler):
    def get_base_dir(self):
        return os.path.join(os.path.dirname(__file__),
                'templates/%s/static' % config.get('template'))
route("/template/static/(.*)", template_static)

class robots:
    def GET(self):
        "no robots/prevent searchengines from indexing"
        web.header("Content-Type", "text/plain")
        print "User-agent: *\nDisallow:/\n"
route("/robots.txt", robots)

class template_style:
    def GET(self):
        web.header("Content-Type", "text/css")
        style = Storage()
        print render.template_style(style)
route("/template_style.css", template_style)

class pixmaps:
    "use the deluge-images. located in data/pixmaps"
    def GET(self, name):
        if not name.endswith('.png'):
            if name == 'paused':
                name = 'inactive'
            if name == 'error':
                name = 'alert'
            name =  name + '16.png'

        if not os.path.exists(get_pixmap(name)):
            name = 'dht16.png'

        f = open(get_pixmap(name) ,'rb')
        fs = os.fstat(f.fileno())
        content = f.read()
        f.close()
        web.header("Content-Type", "image/png")
        web.header("Content-Length", str(fs[6]))
        web.header("Cache-Control" , "public, must-revalidate, max-age=86400")
        print content
route("/pixmaps/(.*)", pixmaps)