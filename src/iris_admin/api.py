from iris_admin import db
import falcon
from falcon import HTTPNotFound
import ujson
import os
import re
import yaml

ui_root = os.environ.get('STATIC_ROOT', os.path.abspath(os.path.dirname(__file__)))
mimes = {'.css': 'text/css',
         '.jpg': 'image/jpeg',
         '.js': 'text/javascript',
         '.png': 'image/png',
         '.svg': 'image/svg+xml',
         '.ttf': 'application/octet-stream',
         '.woff': 'application/font-woff'}


_filename_ascii_strip_re = re.compile(r'[^A-Za-z0-9_.-]')


def secure_filename(filename):
    for sep in os.path.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, ' ')
    filename = str(_filename_ascii_strip_re.sub('', '_'.join(
        filename.split()))).strip('._')
    return filename


class StaticResource(object):
    allow_read_only = True
    frontend_route = False

    def __init__(self, path):
        self.path = path.lstrip('/')

    def on_get(self, req, resp, filename):
        suffix = os.path.splitext(req.path)[1]
        resp.content_type = mimes.get(suffix, 'application/octet-stream')

        filepath = os.path.join(ui_root, self.path, secure_filename(filename))
        try:
            resp.stream = open(filepath, 'rb')
            resp.stream_len = os.path.getsize(filepath)
        except IOError:
            raise HTTPNotFound()


class UsersList:
    def on_get(self, req, resp):
        start_at = req.get_param_as_int('startat', min=0)
        if not start_at:
            start_at = 0
        connection = db.engine.raw_connection()
        cursor = connection.cursor(db.dict_cursor)
        cursor.execute('''SELECT `target`.`name`, `user`.`admin`, `target`.`active`
                          FROM `target`
                          JOIN `user` on `user`.`target_id` = `target`.`id`
                          limit %s, 100''', [start_at])
        resp.body = ujson.dumps(cursor)
        cursor.close()
        connection.close()


class User():
    def on_get(self, req, resp, username):
        connection = db.engine.raw_connection()
        cursor = connection.cursor(db.dict_cursor)
        cursor.execute('''SELECT `target`.`name`, `user`.`admin`, `target`.`active`
                          FROM `target`
                          JOIN `user` on `user`.`target_id` = `target`.`id`
                          WHERE `target`.`name` = %s''', username)
        info = cursor.fetchone()
        cursor.close()

        cursor = connection.cursor()
        cursor.execute('''SELECT `mode`.`name`, `target_contact`.`destination`
        FROM `target_contact`
        JOIN `mode` on `mode`.`id` = `target_contact`.`mode_id`
        JOIN `target` on `target`.`id` = `target_contact`.`target_id`
        WHERE `target`.`name` = %s
        AND `target`.`type_id` = (SELECT `id` FROM `target_type` WHERE `name` = 'user')''', username)
        info['contacts'] = dict(cursor)
        cursor.close()
        connection.close()
        resp.body = ujson.dumps(info)

    def on_put(self, req, resp, username):
        info = ujson.loads(req.stream.read())
        contacts = info['contacts']
        connection = db.engine.raw_connection()
        cursor = connection.cursor(db.dict_cursor)
        cursor.execute('''
            update `target` set `active` = %s
            where `name` = %s
            limit 1
        ''', [info['active'], username])
        cursor.execute('''
            update `user` set `admin` = %s
            where `target_id` = (select `id` from `target` where `name` = %s)
            limit 1
        ''', [info['admin'], username])
        for mode, destination in contacts.iteritems():
            cursor.execute('''INSERT INTO `target_contact` (`target_id`, `mode_id`, `destination`)
                              VALUES (
                                      (SELECT `id` FROM `target` WHERE `name` = %(username)s AND `type_id` = (SELECT `id` FROM `target_type` WHERE `name` = 'user')),
                                      (SELECT `id` FROM `mode` WHERE `name` = %(mode)s),
                                      %(destination)s)
                              ON DUPLICATE KEY UPDATE `destination` = %(destination)s''',
                           {'username': username, 'mode': mode, 'destination': destination})
        cursor.close()
        connection.commit()
        connection.close()
        resp.body = '{}'


def home_route(req, resp):
    resp.content_type = 'text/html'
    resp.body = open('page.html').read()


def get_app(*args, **kwargs):
    config_file = os.environ.get('CONFIG')
    with open(config_file) as h:
        config = yaml.load(h.read())
    db.init(config)
    api = falcon.API()
    api.add_route('/static/{filename}', StaticResource('/static'))
    api.add_route('/api/users', UsersList())
    api.add_route('/api/users/{username}', User())
    api.add_sink(home_route, '/')
    return api
