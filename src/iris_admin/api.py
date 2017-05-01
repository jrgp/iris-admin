from iris_admin import db
import falcon
import ujson
import os
import yaml

class UsersList:
    def on_get(self, req, resp):
        session = db.Session()
        session.close()
     #   users = session.
        return ujson.dumps(users)

def get_app():
    config_file = os.environ.get('CONFIG')
    with open(config_file) as h:
        config = yaml.load(h.read())
    db.init(config)
    api = falcon.API()
    api.add_route('/api/users', UsersList())
