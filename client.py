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
PLANET_COLORS = {
    "Rocky": (180, 140, 100),
    "Gas Giant": (230, 180, 100),
    "Ice World": (200, 230, 255),
    "Volcanic": (255, 90, 60),
    "Ocean": (60, 140, 220),
    "Desert": (230, 200, 120),
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
    small_font = pygame.font.SysFont(None, 22)

    start_networking()
    outgoing.put({"action": "get_region", "params": {"center": [0, 0, 0], "radius": 5}})
    stars = []
    angle_x, angle_y = 0.3, 0.0
    view_radius = 5.0
    view_center = (0, 0, 0)
    star_screen_positions = []  # (screen_x, screen_y, star_dict) for the current frame, used for click detection
    latest_state = {"tick": 0, "you": {"resources": 0}}
    view_mode = "universe"        # "universe" or "system"
    current_system = None         # holds {"star_type": ..., "planets": [...]} once loaded
    entering_system = False       # true right after requesting a system, waiting for the reply
    system_view_radius = 400.0    # zoom level for system view (orbit units, not lightyears)
    system_bodies_screen = []     # (screen_x, screen_y, planet_dict) for click detection in system view
    system_view_center = (0.0, 0.0)   # (x, z) pan offset within the system view — (0,0) = centered on the star
    focused_body = None       # None, {"kind": "star"}, or {"kind": "planet", "planet": planet_dict}
    info_panel_open = False
    star_screen_pos = None    # updated each frame the system is drawn, used for star click detection

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_b:
                outgoing.put({"action": "build", "params": {"cost": 10}})
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_g:
                outgoing.put({"action": "get_system", "params": {"coords": [6, 75, -34]}})
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
                view_mode = "universe"
                current_system = None
                system_view_center = (0.0, 0.0)
                focused_body = None
                info_panel_open = False
            elif event.type == pygame.MOUSEWHEEL:
                if view_mode == "universe":
                    view_radius -= event.y * 0.5
                    view_radius = max(0.5, min(view_radius, 5.0))
                elif view_mode == "system":
                    system_view_radius -= event.y * 40
                    system_view_radius = max(50.0, min(system_view_radius, 2000.0))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            mx, my = event.pos

                            if view_mode == "universe":
                                closest = None
                                closest_dist = 25
                                for sx, sy, star in star_screen_positions:
                                    d = math.hypot(mx - sx, my - sy)
                                    if d < closest_dist:
                                        closest_dist = d
                                        closest = star

                                if closest:
                                    if tuple(closest["coords"]) == tuple(view_center):
                                        # clicking the star you're already centered on -> drill in
                                        entering_system = True
                                        outgoing.put({"action": "get_system", "params": {"coords": list(closest["coords"])}})
                                    else:
                                        # recenter on a different star, same as before
                                        view_center = closest["coords"]
                                        outgoing.put({"action": "get_system", "params": {"coords": list(closest["coords"])}})
                                        outgoing.put({"action": "get_region", "params": {"center": list(closest["coords"]), "radius": 5}})

                            elif view_mode == "system":
                                hit = None  # will become {"kind": "star"} or {"kind": "planet", "planet": ..., "pos": (x, z)}

                                if star_screen_pos:
                                    d = math.hypot(mx - star_screen_pos[0], my - star_screen_pos[1])
                                    if d < 20:
                                        hit = {"kind": "star"}

                                if hit is None:
                                    for sx, sy, planet in system_bodies_screen:
                                        d = math.hypot(mx - sx, my - sy)
                                        if d < 25:
                                            angle_rad = math.radians(planet["angle_deg"])
                                            px = planet["orbit_radius"] * math.cos(angle_rad)
                                            pz = planet["orbit_radius"] * math.sin(angle_rad)
                                            hit = {"kind": "planet", "planet": planet, "pos": (px, pz)}
                                            break

                                if hit:
                                    is_same = (
                                        focused_body is not None
                                        and focused_body["kind"] == hit["kind"]
                                        and (hit["kind"] == "star" or focused_body["planet"]["name"] == hit["planet"]["name"])
                                    )

                                    if info_panel_open:
                                        # any click while the panel is open closes it;
                                        # a click on a different body also refocuses onto it
                                        info_panel_open = False
                                        if not is_same:
                                            focused_body = hit
                                            system_view_center = (0.0, 0.0) if hit["kind"] == "star" else hit["pos"]
                                    else:
                                        if is_same:
                                            info_panel_open = True
                                        else:
                                            focused_body = hit
                                            system_view_center = (0.0, 0.0) if hit["kind"] == "star" else hit["pos"]

        # Drain any messages that arrived from the server
        while not incoming.empty():
            msg = incoming.get()
            if msg.get("type") == "state":
                latest_state = msg["data"]
            elif msg.get("type") == "error":
                print("Server error:", msg["error"])
            elif msg.get("type") == "region":
                stars = msg["data"]
            elif msg.get("type") == "system":
                if entering_system:
                    current_system = msg["data"]
                    view_mode = "system"
                    entering_system = False
                else:
                    print("System data:", msg["data"])

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
        sidebar_width = 350 if (view_mode == "system" and info_panel_open) else 0
        visible_width = screen.get_width() - sidebar_width
        center_x, center_y = visible_width // 2, screen.get_height() // 2

        if view_mode == "universe":
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

        elif view_mode == "system" and current_system:
            fx, fz = system_view_center
            SYSTEM_BASE_SCALE = 6000
            SYSTEM_BASE_RADIUS = 400.0
            scale_factor = SYSTEM_BASE_SCALE * (SYSTEM_BASE_RADIUS / system_view_radius)

            showing_star_panel = (
                info_panel_open and focused_body and focused_body["kind"] == "star"
            )

            # habitable zone shading, only while viewing the star's own stats
            if showing_star_panel:
                hz = current_system["habitable_zone"]
                if hz["outer"] > 0:
                    zone_surface = pygame.Surface((screen.get_width(), screen.get_height()), pygame.SRCALPHA)
                    ZONE_SEGMENTS = 48
                    outer_pts, inner_pts = [], []
                    for i in range(ZONE_SEGMENTS + 1):
                        theta = 2 * math.pi * i / ZONE_SEGMENTS
                        ox = hz["outer"] * math.cos(theta) - fx
                        oz = hz["outer"] * math.sin(theta) - fz
                        osx, osy, _ = project((ox, 0, oz), angle_x, angle_y, distance=600, scale=scale_factor)
                        outer_pts.append((center_x + osx, center_y + osy))

                        ix = hz["inner"] * math.cos(theta) - fx
                        iz = hz["inner"] * math.sin(theta) - fz
                        isx, isy, _ = project((ix, 0, iz), angle_x, angle_y, distance=600, scale=scale_factor)
                        inner_pts.append((center_x + isx, center_y + isy))

                    ring_polygon = outer_pts + list(reversed(inner_pts))
                    pygame.draw.polygon(zone_surface, (60, 200, 90, 70), ring_polygon)
                    screen.blit(zone_surface, (0, 0))

            star_rel = (-fx, 0, -fz)
            sx, sy, sz = project(star_rel, angle_x, angle_y, distance=600, scale=scale_factor)
            star_screen_pos = (int(center_x + sx), int(center_y + sy))
            star_color = STAR_COLORS.get(current_system["star_type"], (255, 255, 255))
            pygame.draw.circle(screen, star_color, star_screen_pos, 14)

            ORBIT_SEGMENTS = 64
            for planet in current_system["planets"]:
                ring_points = []
                for i in range(ORBIT_SEGMENTS + 1):
                    theta = 2 * math.pi * i / ORBIT_SEGMENTS
                    ox = planet["orbit_radius"] * math.cos(theta) - fx
                    oz = planet["orbit_radius"] * math.sin(theta) - fz
                    rsx, rsy, rsz = project((ox, 0, oz), angle_x, angle_y, distance=600, scale=scale_factor)
                    ring_points.append((center_x + rsx, center_y + rsy))
                pygame.draw.aalines(screen, (90, 90, 90), False, ring_points)

            projected = []
            for planet in current_system["planets"]:
                angle_rad = math.radians(planet["angle_deg"])
                px = planet["orbit_radius"] * math.cos(angle_rad) - fx
                pz = planet["orbit_radius"] * math.sin(angle_rad) - fz
                sx, sy, sz = project((px, 0, pz), angle_x, angle_y, distance=600, scale=scale_factor)
                projected.append((sz, sx, sy, planet))
            projected.sort(key=lambda p: -p[0])

            system_bodies_screen = []
            for sz, sx, sy, planet in projected:
                screen_pos = (int(center_x + sx), int(center_y + sy))
                radius = max(2, int(4000 / sz))
                color = PLANET_COLORS.get(planet["type"], (200, 200, 200))
                pygame.draw.circle(screen, color, screen_pos, radius)
                system_bodies_screen.append((screen_pos[0], screen_pos[1], planet))

            if info_panel_open and focused_body:
                panel_x = screen.get_width() - sidebar_width
                pygame.draw.rect(screen, (20, 20, 30), (panel_x, 0, sidebar_width, screen.get_height()))
                pygame.draw.line(screen, (80, 80, 90), (panel_x, 0), (panel_x, screen.get_height()), 2)

                if focused_body["kind"] == "planet":
                    planet = focused_body["planet"]
                    lines = [
                        planet["name"],
                        f"Type: {planet['type']}",
                        f"Size: {planet['size']} km",
                        f"Rich deposit: {planet.get('rich_deposit', '-')}",
                        "",
                        "Resources (ppm):",
                    ]
                    for element, amount in sorted(planet["resources"].items(), key=lambda kv: -kv[1]):
                        lines.append(f"  {element}: {amount:,.6f}")
                else:
                    temp = current_system["star_temp_k"]
                    mass = current_system["star_mass_msun"]
                    hz = current_system["habitable_zone"]
                    lines = [
                        current_system["star_type"],
                        f"Temperature: {temp[0]:,}-{temp[1]:,} K",
                        f"Mass: {mass[0]}-{mass[1]} solar masses",
                        "",
                        "Habitable zone:",
                        f"  {hz['inner']}-{hz['outer']} (orbit units)" if hz["outer"] > 0 else "  None",
                    ]

                y_offset = 20
                for line in lines:
                    text_surface = small_font.render(line, True, (230, 230, 230))
                    screen.blit(text_surface, (panel_x + 15, y_offset))
                    y_offset += 26

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()