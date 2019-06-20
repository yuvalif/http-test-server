import logging
import json 
import BaseHTTPServer
import SocketServer
import threading
import socket
import time
import sys

# configure logging for the tests module
log = logging.getLogger('HTTPTestServer')
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)


class HTTPPostHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_POST(self):
        """implementation of POST handler"""
        try: 
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            log.info('HTTP Server (%d) received event: %s', self.server.worker_id, str(body))
        except:
            log.error('HTTP Server received empty event: %s', str(body))
            self.send_response(400)
        else:
            self.send_response(100)
        finally:
            self.end_headers()


class ThreadedHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    def __init__(self, addr, handler):
        BaseHTTPServer.HTTPServer.__init__(self, addr, handler)
        self.worker_id = threading.currentThread().ident

class HTTPServerWithID(BaseHTTPServer.HTTPServer):
    def __init__(self, addr, handler, worker_id, bind_address=True):
        BaseHTTPServer.HTTPServer.__init__(self, addr, handler, bind_address)
        self.worker_id = worker_id

class HTTPServerThread(threading.Thread):
    def __init__(self, i, sock, addr):
        threading.Thread.__init__(self)
        self.i = i
        self.daemon = True
        self.httpd = HTTPServerWithID(addr, HTTPPostHandler, i, False)
        self.httpd.socket = sock
        # prevent the HTTP server from re-binding every handler
        self.httpd.server_bind = self.server_close = lambda self: None
        self.start()

    def run(self):
        try:
            log.info('HTTP Server (%d) started on: %s', self.i, self.httpd.server_address)
            self.httpd.serve_forever()
            log.info('HTTP Server (%d) ended', self.i)
        except Exception as error:
            # could happen if the server r/w to a closing socket during shutdown
            log.info('HTTP Server (%d) ended unexpectedly: %s', self.i, str(error))

    def close(self):
        """ close the http server """
        self.httpd.shutdown()


class StreamingHTTPServer:
    """multithreaded streaming server, based on: https://stackoverflow.com/questions/46210672/"""
    def __init__(self, host, port, num_workers=100):
        addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(addr)
        # maximum of 10 connection backlog on the listener
        self.sock.listen(10)
        self.workers = [HTTPServerThread(i, self.sock, addr) for i in range(num_workers)]

    def close(self):
        """close all workers in the http server and wait for it to finish"""
        # make sure that the shared socket is closed
        # this is needed in case that one of the threads is blocked on the socket
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()
        # wait for server threads to finish
        for worker in self.workers:
            worker.close()
            worker.join()

# 0 - single threaded
# 1 - multi threaded
# 2 - multi threaded streaming
server_type = 2

if __name__== "__main__":
    if len(sys.argv) != 3:
        print 'usage: %s <host> <port>' % sys.argv[0]
        exit(1)
    host = sys.argv[1]
    port = int(sys.argv[2])
    if server_type == 0:
        httpd = HTTPServerWithID((host, port), HTTPPostHandler, 1)
        log.info('HTTP Server (1) started on: %s', (host, port))
        httpd.serve_forever()
        log.info('HTTP Server (1) ended')
    elif server_type == 1:
        httpd = ThreadedHTTPServer((host, port), HTTPPostHandler)
        log.info('Multi-threaded HTTP Server started on: %s', (host, port))
        httpd.serve_forever()
        log.info('Multi-threaded HTTP Server ended')
    elif server_type == 2:
        httpd = StreamingHTTPServer(host, port, 10)
        while True:
            time.sleep(1)
