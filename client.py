import pygame
import socket
import json
import threading
import queue
import time
import math

HOST, PORT = '127.0.0.1', 5555
POLL_INTERVAL = 0.5  # seconds between state pulls — tune to taste

incoming = queue.Queue()   # server -> main thread
outgoing = queue.Queue()   # main thread -> server (manual commands, e.g. build)

sock = None
sock_file = None
send_lock = threading.Lock()
PLAYER_NAME = "Connor"

def reader_thread():
    while True:
        line = sock_file.readline()
        if not line:
            break
        incoming.put(json.loads(line))

def writer_thread():
    last_poll = 0
    while True:
        try:
            cmd = outgoing.get(timeout=0.05)
            with send_lock:
                sock.sendall((json.dumps(cmd) + "\n").encode())
        except queue.Empty:
            pass

        now = time.time()
        if now - last_poll >= POLL_INTERVAL:
            with send_lock:
                sock.sendall((json.dumps({"action": "get_state"}) + "\n").encode())
            last_poll = now
def project(point, angle_x, angle_y, distance=30, scale=4000):
    x, y, z = point
    # rotate around Y axis (left/right)
    cosy, siny = math.cos(angle_y), math.sin(angle_y)
    x, z = x * cosy - z * siny, x * siny + z * cosy
    # rotate around X axis (up/down)
    cosx, sinx = math.cos(angle_x), math.sin(angle_x)
    y, z = y * cosx - z * sinx, y * sinx + z * cosx

    z += distance
    if z < 0.5:
        z = 0.5  # avoid divide-by-near-zero / behind-camera flip

    factor = scale / z
    screen_x = x * factor
    screen_y = y * factor
    return screen_x, screen_y, z

STAR_COLORS = {
    "Red Dwarf": (255, 100, 80),
    "Yellow Star": (255, 230, 120),
    "Blue Giant": (140, 180, 255),
    "White Dwarf": (240, 240, 255),
    "Neutron Star": (200, 255, 255),
}
def start_networking():
    global sock, sock_file
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    sock_file = sock.makefile('r')

    # Say hello before anything else
    sock.sendall((json.dumps({"action": "hello", "name": PLAYER_NAME}) + "\n").encode())

    threading.Thread(target=reader_thread, daemon=True).start()
    threading.Thread(target=writer_thread, daemon=True).start()

def main():
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("A Space Game")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 36)

    start_networking()
    outgoing.put({"action": "get_region", "params": {"center": [0, 0, 0], "radius": 5}})
    stars = []
    angle_x, angle_y = 0.3, 0.0
    view_radius = 5.0
    view_center = (0, 0, 0)
    star_screen_positions = []  # (screen_x, screen_y, star_dict) for the current frame, used for click detection
    latest_state = {"tick": 0, "you": {"resources": 0}}

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_b:
                outgoing.put({"action": "build", "params": {"cost": 10}})
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_g:
                outgoing.put({"action": "get_system", "params": {"coords": [6, 75, -34]}})
            elif event.type == pygame.MOUSEWHEEL:
                view_radius -= event.y * 0.5
                view_radius = max(0.5, min(view_radius, 5.0))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                closest = None
                closest_dist = 25
                for sx, sy, star in star_screen_positions:
                    d = math.hypot(mx - sx, my - sy)
                    if d < closest_dist:
                        closest_dist = d
                        closest = star
                if closest:
                    view_center = closest["coords"]
                    outgoing.put({"action": "get_system", "params": {"coords": list(closest["coords"])}})
                    outgoing.put({"action": "get_region", "params": {"center": list(closest["coords"]), "radius": 5}})

        # Drain any messages that arrived from the server
        while not incoming.empty():
            msg = incoming.get()
            if msg.get("type") == "state":
                latest_state = msg["data"]
            elif msg.get("type") == "error":
                print("Server error:", msg["error"])
            elif msg.get("type") == "system":
                print("System data:", msg["data"])
            elif msg.get("type") == "region":
                stars = msg["data"]

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            angle_y -= 0.02
        if keys[pygame.K_RIGHT]:
            angle_y += 0.02
        if keys[pygame.K_UP]:
            angle_x -= 0.02
        if keys[pygame.K_DOWN]:
            angle_x += 0.02

        screen.fill((5, 5, 15))
        center_x, center_y = screen.get_width() // 2, screen.get_height() // 2

        cx, cy, cz = view_center
        projected = []
        for star in stars:
            x, y, z = star["coords"]
            rel = (x - cx, y - cy, z - cz)
            dist = math.sqrt(rel[0]**2 + rel[1]**2 + rel[2]**2)
            if dist > view_radius:
                continue
            sx, sy, sz = project(rel, angle_x, angle_y)
            projected.append((sz, sx, sy, star["star_type"], star))
        projected.sort(key=lambda s: -s[0])

        star_screen_positions = []
        for sz, sx, sy, star_type, star in projected:
            screen_pos = (int(center_x + sx), int(center_y + sy))
            radius = max(1, int(200 / sz))
            color = STAR_COLORS.get(star_type, (255, 255, 255))
            pygame.draw.circle(screen, color, screen_pos, radius)
            star_screen_positions.append((screen_pos[0], screen_pos[1], star))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()