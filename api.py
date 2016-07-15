from flask import Flask
from flask_restful import Resource, Api, reqparse
import urllib
import http
import subprocess
import signal
import os
import time

app = Flask(__name__)
api = Api(app)

parser = reqparse.RequestParser()
parser.add_argument('config', type=str, help='plain toml text')
parser.add_argument('oname', type=str, help='name for output file')
parser.add_argument('username', type=str, help='username')

running = None

timeout = 7200


def kill_build(running):
    os.killpg(os.getpgid(running['process'].pid), signal.SIGTERM)


def check_timeout():
    global running
    if running is not None:
        if time.time() - running['start'] > timeout:
            kill_build(running)
            return 'terminated'
        return 'running'
    return 'no process'


class Build(Resource):
    def put(self):
        global running
        if running is None:
            print('Starting build ...')
            args = parser.parse_args()
            print(args)
            # with urllib.request.urlopen(args['furl']) as response:
            #     toml = response.read().decode('utf-8')
            # print(toml)
            os.chdir(os.path.expanduser('~/apricity-build'))
            with open('freezedry/gen.toml', 'w') as f:
                f.write(args['config'])
            cmd = ['bash', 'buildpush.sh', '-v',
                   '-R', 'true',
                   '-E', 'gen',
                   '-U', args['username'],
                   '-N', args['oname']]
            running = {
                'oname': args['oname'],
                'start': time.time(),
                'process': subprocess.Popen(
                    cmd, preexec_fn=os.setsid)
            }
            return {'status': 'success'}, 201
        return {'status': 'failure',
                'message': 'something is already running'}, 201

    def delete(self):
        global running
        if running is not None:
            kill_build(running)
            running = None
            return {'status': 'success',
                    'message': 'build killed'}, 201
        else:
            return {'status': 'failure',
                    'message': 'nothing to kill'}, 201

    def get(self):
        global running
        if running is not None:
            if running['process'].poll() == 0:  # built successfully
                desturl = 'https://apricityos.com/freezedry-build/%s.iso' % \
                    running['oname']
                print('Looking for url response ...')
                url = urllib.parse.urlparse(desturl)
                conn = http.client.HTTPConnection(url.netloc)
                conn.request('HEAD', url.path)
                res = conn.getresponse()
                if res.status == 200:
                    return {'status': 'success',
                            'message': 'build completed'}, 201
                else:
                    return {'status': 'failure',
                            'message': 'build/upload failed but exited 0'}, 201
            elif running['process'].poll() is not None:  # build failed
                return{'status': 'failure',
                       'message': 'build failed with exitcode',
                       'exitcode': running['process'].poll()}, 201
            else:  # still running
                timeout = check_timeout()
                if timeout == 'terminated':
                    return {'status': 'failure',
                            'message': 'killed on timeout'}, 201
                elif timeout == 'no process':
                    return {'status': 'failure',
                            'message': 'internal server error'}, 501
                return {'status': 'not completed'}, 201
        else:
            return {'status': 'failure',
                    'message': 'nothing running'}, 201

api.add_resource(Build, '/build')

if __name__ == '__main__':
    app.run(debug=True)
