#!/usr/bin/env python3
"""启动本地 HTTP 服务器，访问 http://localhost:8765 查看仪表盘"""
import http.server, socketserver, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PORT = 8765

class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
        '.csv': 'text/csv', '.json': 'application/json'}

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"\n  Predictive Maintenance Dashboard")
    print(f"  http://localhost:{PORT}")
    print(f"  serving: {os.getcwd()}")
    print(f"\n  Press Ctrl+C to stop\n")
    httpd.serve_forever()
