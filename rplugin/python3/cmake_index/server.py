#
# Copyright © 2017 Maks Mazurov (fox.cpp)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import string
import os
import socket
import subprocess
import time
import json
import random
import logging


def randomword(length):
    return ''.join(random.choice(string.ascii_lowercase) for i in range(length))


class CmakeError(Exception):
    pass


class CmakeServer(object):
    __slots__ = ('root_dir', 'build_dir', 'socket_path', 'process', 'logger',
                 'socket', 'socket_file', 'msg_handler', 'signal_handler')

    def __init__(self) -> None:
        self.logger = logging.getLogger('cmake_index.nvim')
        self.root_dir: str = None
        self.build_dir: str = None
        self.socket_path: str = None
        self.process: subprocess.Popen = None
        self.socket: socket.SocketType = None
        # Creation of socket_file each time before read results in lost message somehow.
        self.socket_file: socket.SocketIO = None
        self.socket_path: str = None

    def __del__(self):
        if self.process is not None:
            self.process.poll()
            self.process.terminate()
            time.sleep(0.4)
            self.process.poll()
            if self.process.returncode is None:
                self.process.poll()
                self.process.kill()
                self.logger.warning('Server force-terminated.')
                self.process.poll()  # request status code to prevent creating zombie processes
            os.unlink(self.socket_path)

    def signal(self, json: dict) -> None:
        pass

    def msg(self, json: dict) -> None:
        if 'CMake Error' in json['message']:
            self.logger.error(json['message'])
        else:
            self.logger.debug('cmake: ' + json['message'])

    def start(self, cmake_binary: str, socket_path: str) -> None:
        if self.process is not None or self.socket is not None:
            raise CmakeError('Already started')

        self.logger.debug('Starting cmake server...')
        self.process = subprocess.Popen(
            [cmake_binary, '-E', 'server', '--pipe=' + socket_path, '--experimental'])
        self.socket_path = socket_path

        if self.process.returncode is not None:
            raise CmakeError('Server terminated right after starting.')

        tries = 0
        while tries < 10 and not os.path.exists(socket_path):
            time.sleep(0.5)
        self.process.poll()
        if self.process.returncode is not None:
            raise CmakeError('Server terminated right after starting.')
        if not os.path.exists(socket_path):
            raise CmakeError('Server startup is too long (> 5 seconds). Is everything fine?')

        self.logger.debug('Server seems to be running, connecting... (PID: %d, UDS: %s)',
                          self.process.pid, self.socket_path)

        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.connect(socket_path)
        self.socket_file = self.socket.makefile('rw')
        hello = self.read_message()

        server_supports_1x = False
        for supported_protocol in hello['supportedProtocolVersions']:
            if supported_protocol['major'] == 1:
                server_supports_1x = True
        if not server_supports_1x:
            raise CmakeError('Server doesn\'t support 1.x protocol.')

    def handshake(self, root_dir: str, build_dir: str, generator) -> None:
        if self.root_dir is not None or self.build_dir is not None:
            raise CmakeError('Already handshak\'ed')
        self.root_dir = root_dir
        self.build_dir = build_dir
        self.logger.debug('Setting up server for the project in %s (building in %s)...', self.root_dir, self.build_dir)
        if generator is None:
            self.send_and_read({
                'type': 'handshake',
                'sourceDirectory': root_dir,
                'buildDirectory': build_dir,
                'protocolVersion': {'major': 1},
            })
        else:
            self.send_and_read({
                'type': 'handshake',
                'sourceDirectory': root_dir,
                'buildDirectory': build_dir,
                'protocolVersion': {'major': 1},
                'generator': generator
            })

    def configure(self, cache_entries=dict()) -> None:
        self.logger.debug('Updating project configuration...')
        self.send_and_read({
            'type': 'configure',
            'cacheArguments': ['-D' + k + '=' + v for (k, v) in cache_entries.items()]
        })

    def generate(self):
        self.logger.debug('Generating build system...')
        return self.send_and_read({'type': 'compute'})

    def codemodel(self):
        self.logger.debug('Requesting project model...')
        return self.send_and_read({'type': 'codemodel'})

    def cache(self):
        self.logger.debug('Requesting cache variables...')
        return self.send_and_read({'type': 'cache'})

    def read_message(self) -> dict:
        if self.process is None or self.socket is None or self.process.returncode is not None:
            # if self.process.returncode = None, then zero handles since process terminated.
            self.process = None
            self.socket = None
            raise CmakeError('Server is not running.')
        self.check_server_status()
        lines = list()
        line_buf = str()
        while line_buf != ']== "CMake Server" ==]':
            self.check_server_status()
            line_buf = self.socket_file.readline().strip()
            if len(line_buf) != 0:
                lines.append(line_buf)
        return json.loads('\n'.join(lines[1:-1]))

    def send_message(self, message: dict) -> None:
        if self.process is None or self.socket is None or self.process.returncode is not None:
            # if self.process.returncode = None, then zero handles since process terminated.
            self.process = None
            self.socket = None
            raise CmakeError('Server is not running.')
        self.check_server_status()

        # self.socket_file is not used because it would require recreating it each time
        # in order to force send.

        with self.socket.makefile('w') as socket_file:
            socket_file.write('[== "CMake Server" ==[\n')
            socket_file.write(json.dumps(message) + '\n')
            socket_file.write(']== "CMake Server" ==]\n')

    def send_and_read(self, message: dict) -> dict:
        message['cookie'] = randomword(8)
        self.send_message(message)
        resp_msg = self.read_message()
        while resp_msg['type'] != 'reply':
            if resp_msg['type'] == 'signal':
                self.signal(resp_msg)
            if resp_msg['type'] == 'message':
                self.msg(resp_msg)
            if resp_msg['type'] == 'error':
                raise CmakeError(resp_msg['errorMessage'])
            resp_msg = self.read_message()
        return resp_msg

    def check_server_status(self) -> None:
        self.process.poll()
        if self.process.returncode is not None and self.process.returncode != 0:
            raise CmakeError('Cmake server crashed. Return code: ' +
                             str(self.process.returncode) + '.')
