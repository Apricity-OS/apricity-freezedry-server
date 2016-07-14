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
parser.add_argument('furl', type=str, help='url with freezedry toml config')
parser.add_argument('fname', type=str, help='name of freezedry toml config')
parser.add_argument('oname', type=str, help='name for output file')

# running = {
#     'fname': None,
#     'oname': None,
#     'start': None,
# }

running = None

timeout = 7200


def kill_build(running):
    os.killpg(os.getpgid(running['process'].pid), signal.SIGTERM)


def check_timeout():
    global running
    if running is not None:
        if time.time() - running['start'] > timeout:
            kill_build(running)
            running = None
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
            with urllib.request.urlopen(args['furl']) as response:
                toml = response.read().decode('utf-8')
            print(toml)
            os.chdir(os.path.expanduser('~/apricity-build'))
            with open('freezedry/%s.toml' % args['fname'], 'w') as f:
                f.write(toml)
            cmd = ['bash', 'buildpush.sh', '-v',
                   '-E', args['fname'],
                   '-R', 'true',
                   '-N', args['oname']]
            running = {
                'fname': args['fname'],
                'oname': args['oname'],
                'start': time.time(),
                'process': subprocess.Popen(
                    cmd, preexec_fn=os.setsid)
            }
            return {'status': 'success'}, 201
        return {'status': 'failure'}, 201

    def delete(self):
        global running
        if running is not None:
            kill_build(running)
            running = None
            return {'status': 'success'}
        else:
            return {'status': 'nothing to kill'}

    def get(self):
        global running
        if running is not None:
            print('Checking ...')
            if running['process'].poll() == 0:  # built successfully
                desturl = 'https://apricityos.com/freezedry-build/%s.iso' % \
                    running['oname']
                print('Looking for url response ...')
                url = urllib.parse.urlparse(desturl)
                conn = http.client.HTTPConnection(url.netloc)
                conn.request('HEAD', url.path)
                res = conn.getresponse()
                if res.status == 200:
                    running = None
                    return {'status': 'completed'}, 201
                else:
                    return {'status': 'build/upload failed but exited 0'}, 201
            elif running['process'].poll() is not None:
                return{'status': 'build failed',
                       'exitcode': running['process'].poll()}, 201
            else:  # only terminate if not completed
                timeout = check_timeout()
                if timeout == 'terminated':
                    return {'status': 'terminated'}, 201
                elif timeout == 'no process':
                    return '', 501
                return {'status': 'not completed'}, 201
        else:
            return {'status': 'not running'}, 201

api.add_resource(Build, '/build')

if __name__ == '__main__':
    app.run(debug=True)
