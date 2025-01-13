import os
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn


class CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "x-api-key, Content-Type")
        SimpleHTTPRequestHandler.end_headers(self)

    def list_directory(self, path):
        try:
            list = os.listdir(path)
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None
        list.sort(key=lambda a: a.lower())
        r = []
        displaypath = self.path
        r.append(f"<!DOCTYPE html><html><head><title>Directory listing for {displaypath}</title></head>")
        r.append(
            '<div style="text-align: right; margin: 20px;"><button style="background-color: #2986cc; color: \
             white; padding: 10px 20px; border: none; border-radius: 5px; font-size: 16px; cursor: pointer;" \
             onclick="stopServer()">🛑 Stop Server</button></div>'
        )
        r.append(
            f'<h2><a href="https://radiantearth.github.io/stac-browser/#/external/http://localhost:{self.server.server_port}/catalog.json" target="_blank">STAC Viewer</a></h2>'
        )
        r.append(f"<body><h4>Local directory listing for {displaypath}</h4>")

        r.append(
            """
            <script>
                function stopServer() {
                    fetch('/shutdown', { method: 'POST' })
                    .then(response => response.text())
                    .then(data => {
                        alert(data);
                        window.close();
                    })
                    .catch(error => alert('Failed to stop server'));
                }
            </script>
        """
        )

        r.append("<hr><ul>")
        for name in list:
            fullname = os.path.join(path, name)
            displayname = name
            linkname = name
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
            r.append(f'<li><a href="{linkname}">{displayname}</a></li>')
        r.append("</ul><hr>")
        r.append("</body></html>")
        encoded = "\n".join(r).encode("utf-8", "surrogateescape")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
        return None

    def do_POST(self):
        if self.path == "/shutdown":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"Server is shutting down...")
            print("Shutting down the server...")

            def shutdown():
                self.server.shutdown()

            import threading

            threading.Thread(target=shutdown).start()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""


def main(mkdir: bool = True):
    if len(sys.argv) < 2:
        print("Usage: python server.py <directory_to_serve> [host] [port]")
        sys.exit(1)

    local_dir = sys.argv[1]
    if not os.path.isdir(local_dir):
        if mkdir:
            os.makedirs(local_dir)
        else:
            print(
                f"The specified directory '{local_dir}' does not exist or is not a directory., set mkdir=True to create it."
            )
            sys.exit(1)

    os.chdir(local_dir)

    host = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 5000

    print(f"Serving '{local_dir}' on {host}:{port}")
    httpd = ThreadedHTTPServer((host, port), CORSRequestHandler)

    url = f"http://localhost:{port}/"
    webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down the server.")
        httpd.server_close()


if __name__ == "__main__":
    main()
