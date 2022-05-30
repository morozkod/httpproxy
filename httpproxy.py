#!/usr/local/bin/python3.10
import sys
import socket
import select
import httptools as htools
import threading
import argparse

# For best match with hardware and network realities,
# the value of bufsize should be a relatively small power of 2, for example, 4096
BUFSIZE = 4096

HTTP_OK_RESPONSE = b'HTTP/1.1 200 OK\r\n\n'

class HtoolsProto:
    def __init__(self):
        self.done = False

    def on_url(self, url):
        self.url = url
        print(f'Got url: {url}')

    def on_message_complete(self):
        self.done = True
        print('Parsing done')

def has_prefix(url):
    return b'://' in url

def __parse_url_https(url):
    parsed_url = htools.parse_url(url)

    host = parsed_url.host
    port = parsed_url.port

    if port == None:
        schema = parsed_url.schema
        if schema == b'http':
            port = 80
        elif schema == b'https':
            port = 443
        else:
            print(f'Unexpected schema: {schema}')

    return (host, port)

def __parse_url_http(url):
    if not has_prefix(url): # Dirty hack
        url = b'https://' + url

    info = __parse_url_https(url)

    return info

def parse_url(url):
    if b'https' in url:
        info = __parse_url_https(url)
    else:
        info = __parse_url_http(url)

    return info

def socket_create_and_listen(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen()

    return s

def socket_create_and_connect(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))

    return s

def handle_connection(client_sock):
    proto = HtoolsProto()
    parser = htools.HttpRequestParser(proto)
    buffer = b''

    while not proto.done:
        data = client_sock.recv(BUFSIZE)
        if not data:
            return

        try:
            parser.feed_data(data)
        except htools.HttpParserUpgrade as e:
            offset = e.args[0]
            print("Incomplete data, waiting..")

        buffer += data

    method = parser.get_method()

    print(f'Got an {method} request')

    requested_conn_info = parse_url(proto.url)

    print(f'Client wants to connect to {requested_conn_info[0]}:{requested_conn_info[1]}')

    try:
        server_sock = socket_create_and_connect(*requested_conn_info)
    except Exception:
        print('Could not create socket or connect')
        return

    if method == b'CONNECT':
        client_sock.sendall(HTTP_OK_RESPONSE)
        if offset < len(data):
            server_sock.sendall(data[offset:]) #last processed chunk of data
    else:
        server_sock.sendall(buffer)

    server_sock.setblocking(False);
    client_sock.setblocking(False);

    while True:
        sockets = select.select([server_sock, client_sock], [], [])

        for s in sockets[0]:
            corresponding_socket = client_sock if s == server_sock else server_sock
            data = s.recv(BUFSIZE)

            try:
                corresponding_socket.sendall(data)
            except Exception:
                print('Could not create sendall')
                return

def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("port", help="port for the http proxy to use")
    args = argparser.parse_args()

    s = socket_create_and_listen("localhost", int(args.port))

    while True:
        client_sock, client_addr = s.accept()
        print(f'{str(client_addr)}: Connection established')
        threading.Thread(target=handle_connection, args=(client_sock,), daemon=True).start()

if __name__ == "__main__":
    main()
