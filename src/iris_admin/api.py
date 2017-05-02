from iris_admin import db
import falcon
from falcon import HTTPNotFound
import ujson
import os
import re
import yaml
import phonenumbers
import logging


logger = logging.getLogger(__name__)

ui_root = os.path.abspath(os.path.dirname(__file__))
mimes = {'.css': 'text/css',
         '.jpg': 'image/jpeg',
         '.js': 'text/javascript',
         '.png': 'image/png',
         '.svg': 'image/svg+xml',
         '.ttf': 'application/octet-stream',
         '.woff': 'application/font-woff'}


_filename_ascii_strip_re = re.compile(r'[^A-Za-z0-9_.-]')


def normalize_phone_number(number):
    return phonenumbers.format_number(phonenumbers.parse(number, 'US'), phonenumbers.PhoneNumberFormat.INTERNATIONAL)


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

        startswith = req.get_param('startswith')

        query = '''SELECT `target`.`name`, `user`.`admin`, `target`.`active`
                   FROM `target`
                   JOIN `user` on `user`.`target_id` = `target`.`id` '''
        wheres = []

        if startswith:
            query += 'WHERE `target`.`name` LIKE %s'
            wheres.append(startswith + '%')

        query += 'LIMIT %s, 100'
        wheres.append(start_at)

        connection = db.engine.raw_connection()
        cursor = connection.cursor(db.dict_cursor)
        cursor.execute(query, wheres)
        resp.body = ujson.dumps(cursor)
        cursor.close()
        connection.close()

    def on_post(self, req, resp):
        username = ujson.loads(req.stream.read())['username']

        connection = db.engine.raw_connection()
        cursor = connection.cursor(db.dict_cursor)
        cursor.execute('''INSERT INTO `target` (`name`, `type_id`, `active`)
                          VALUES (%s, (SELECT `id` FROM `target_type` WHERE `name` = 'user'), TRUE)''', username)
        user_id = cursor.lastrowid
        connection.commit()

        cursor.execute('''INSERT INTO `user` (`target_id`, `admin`) VALUES (%s, FALSE) ''', user_id)
        cursor.close()
        connection.commit()
        connection.close()
        resp.body = '{}'


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

        cursor.execute('''SELECT `name` FROM `mode` WHERE `name` != 'drop' ''')
        for (mode,) in cursor:
            info['contacts'].setdefault(mode, '')

        cursor.close()
        connection.close()
        resp.body = ujson.dumps(info)

    def on_put(self, req, resp, username):
        info = ujson.loads(req.stream.read())
        contacts = info['contacts']
        connection = db.engine.raw_connection()
        cursor = connection.cursor(db.dict_cursor)
        cursor.execute('''
            UPDATE `target` SET `active` = %s
            WHERE `name` = %s
            LIMIT 1
        ''', [info['active'], username])
        cursor.execute('''
            UPDATE `user` SET `admin` = %s
            WHERE `target_id` = (SELECT `id` FROM `target` WHERE `name` = %s)
            LIMIT 1
        ''', [info['admin'], username])
        for mode, destination in contacts.iteritems():

            destination = destination.strip()
            if mode in ('call', 'sms'):
                try:
                    old_destination = destination
                    destination = normalize_phone_number(destination)
                    if old_destination != destination:
                        logger.info('Normalized %s to %s', old_destination, destination)
                except Exception:
                    logger.exception('Failed normalizing phone number %s', destination)

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

    def on_delete(self, req, resp, username):
        connection = db.engine.raw_connection()
        cursor = connection.cursor(db.dict_cursor)
        cursor.execute('''DELETE FROM `target`
                          WHERE `name` = %s
                          AND `type_id` = (SELECT `id` FROM `target_type` WHERE `name` = 'user')
                          LIMIT 1''', username)
        cursor.close()
        connection.commit()
        connection.close()
        resp.body = '{}'


def home_route(req, resp):
    resp.content_type = 'text/html'
    resp.body = open(os.path.join(ui_root, 'static/spa.html')).read()


def get_app():
    logging.basicConfig(format='[%(asctime)s] [%(process)d] [%(levelname)s] %(name)s %(message)s',
                        level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S %z')
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
