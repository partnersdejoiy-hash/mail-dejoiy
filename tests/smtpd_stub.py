"""A tiny one-message SMTP server for tests (no network beyond localhost)."""
import socket, threading

def run(send):
    srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1); port = srv.getsockname()[1]; data = []
    def serve():
        c, _ = srv.accept(); f = c.makefile('rwb')
        def say(line): f.write(line.encode() + b'\r\n'); f.flush()
        say('220 stub'); body = False
        for raw in f:
            line = raw.decode(errors='replace').rstrip('\r\n')
            if body:
                if line == '.': body = False; say('250 ok'); continue
                data.append(line); continue
            cmd = line[:4].upper()
            if cmd in ('EHLO', 'HELO'): say('250 stub')
            elif cmd == 'DATA': body = True; say('354 go')
            elif cmd == 'QUIT': say('221 bye'); break
            else: say('250 ok')
        c.close(); srv.close()
    t = threading.Thread(target=serve, daemon=True); t.start()
    send(port); t.join(5)
    return '\n'.join(data)
