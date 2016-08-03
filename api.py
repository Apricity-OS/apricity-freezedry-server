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

iso_parser = reqparse.RequestParser()
iso_parser.add_argument('config', type=str, help='plain toml text')
iso_parser.add_argument('oname', type=str, help='name for output file')
iso_parser.add_argument('username', type=str, help='username')
iso_parser.add_argument(
    'num', type=int,
    help='build number (unique for oname+username combination)')

running_iso = None

timeout = 7200


def kill_iso_build(running_iso):
    os.killpg(os.getpgid(running_iso['process'].pid), signal.SIGTERM)


def check_iso_timeout():
    global running_iso
    if running_iso is not None:
        if time.time() - running_iso['start'] > timeout:
            kill_iso_build(running_iso)
            return 'terminated'
        return 'running_iso'
    return 'no process'


class Build(Resource):
    def put(self):
        global running_iso
        if running_iso is None:
            print('Starting build ...')
            args = iso_parser.parse_args()
            print(args)
            # with urllib.request.urlopen(args['furl']) as response:
            #     toml = response.read().decode('utf-8')
            # print(toml)
            os.chdir('/home/server/apricity-build')
            with open('freezedry/gen.toml', 'w') as f:
                f.write(args['config'])
            cmd = ['bash', 'buildpush.sh', '-v',
                   '-R', 'true',
                   '-E', 'gen',
                   '-U', args['username'],
                   '-N', '%s-%d' % (args['oname'], args['num'])]
            running_iso = {
                'oname': args['oname'],
                'num': args['num'],
                'username': args['username'],
                'start': time.time(),
                'process': subprocess.Popen(
                    cmd, preexec_fn=os.setsid)
            }
            return {'status': 'success'}, 201
        return {'status': 'failure',
                'message': 'something is already running'}, 201

    def delete(self):
        global running_iso
        if running_iso is not None:
            try:
                kill_iso_build(running_iso)
            except Exception as e:
                print(e)
            running_iso = None
            return {'status': 'success',
                    'message': 'build killed'}, 201
        else:
            return {'status': 'failure',
                    'message': 'nothing to kill'}, 201

    def get(self):
        if running_iso is not None:
            if running_iso['process'].poll() == 0:  # built successfully
                desturl = ('https://static.apricityos.com/freezedry-build'
                           '/%s/apricity_os-%s-%d.iso' %
                           (running_iso['username'],
                            running_iso['oname'],
                            running_iso['num']))
                print('Looking for url response ...')
                url = urllib.parse.urlparse(desturl)
                conn = http.client.HTTPSConnection(url.netloc)
                conn.request('HEAD', url.path)
                res = conn.getresponse()
                if res.status == 200:
                    return {'status': 'success',
                            'message': 'build completed'}, 201
                else:
                    return {'status': 'failure',
                            'message': 'build/upload failed but exited 0'}, 201
            elif running_iso['process'].poll() is not None:  # build failed
                return{'status': 'failure',
                       'message': 'build failed with exitcode',
                       'exitcode': running_iso['process'].poll()}, 201
            else:  # still running
                timeout = check_iso_timeout()
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


class SingleBuild(Resource):
    def delete(self, username, iso_name):
        os.chdir('/home/server/apricity-build')
        cmd = ['bash', 'deletebuild.sh',
               '-U', username,
               '-N', iso_name]
        subprocess.call(cmd)
        return {'status': 'success'}, 201

api.add_resource(SingleBuild, '/build/<string:username>/<string:iso_name>')

repo_parser = reqparse.RequestParser()
repo_parser.add_argument('package_name', type=str,
                         help='package name (i.e. google-chrome)')
repo_parser.add_argument('repo_name', type=str,
                         help='repo name (i.e. apricity-core)')
repo_parser.add_argument('repo_endpoint', type=str,
                         help='repo endpoint (i.e. apricity-core-signed)')

running_repo = None

repo_timeout = 3600


def kill_repo_build(running_repo):
    os.killpg(os.getpgid(running_repo['process'].pid), signal.SIGTERM)


def check_repo_timeout():
    global running_repo
    if running_repo is not None:
        if time.time() - running_repo['start'] > timeout:
            kill_build(running_repo)
            return 'terminated'
        return 'running_repo'
    return 'no process'


class Repo(Resource):
    def put(self):
        global running_repo
        if running_repo is None:
            print('Starting package ...')
            args = repo_parser.parse_args()
            print(args)
            os.chdir('/home/server/apricity-repo')
            cmd = ['bash', 'buildpush.sh',
                   '-P', args['package_name'],
                   '-R', args['repo_name'],
                   '-E', args['repo_endpoint']]
            running_repo = {
                'package_name': args['package_name'],
                'repo_name': args['repo_name'],
                'repo_endpoint': args['repo_endpoint'],
                'start': time.time(),
                'process': subprocess.Popen(
                    cmd, preexec_fn=os.setsid)
            }
            return {'status': 'success'}, 201
        return {'status': 'failure',
                'message': 'something is already running'}, 201

    def delete(self):
        global running_repo
        if running_repo is not None:
            try:
                kill_repo_build(running_repo)
            except Exception as e:
                print(e)
            running_repo = None
            return {'status': 'success',
                    'message': 'build killed'}, 201
        else:
            return {'status': 'failure',
                    'message': 'nothing to kill'}, 201

    def get(self):
        global running_repo
        if running_repo is not None:
            if running_repo['process'].poll() == 0:  # built successfully
                return {'status': 'success',
                        'message': 'build completed'}, 201
            elif running_repo['process'].poll() is not None:  # build failed
                return{'status': 'failure',
                       'message': 'build failed with exitcode',
                       'exitcode': running_repo['process'].poll()}, 201
            else:  # still running
                timeout = check_repo_timeout()
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


api.add_resource(Repo, '/repo')

if __name__ == '__main__':
    app.run(debug=True)
