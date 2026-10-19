import pygame
import socket
import json
import threading
import queue
import time
import math

HOST, PORT = '127.0.0.1', 5555
POLL_INTERVAL = 0.5

incoming = queue.Queue()
outgoing = queue.Queue()

sock = None
sock_file = None
send_lock = threading.Lock()
PLAYER_NAME = "Connor"

AU_SCALE = 100  # render units per astronomical unit

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
        except OSError:
            break

        now = time.time()
        if now - last_poll >= POLL_INTERVAL:
            try:
                with send_lock:
                    sock.sendall((json.dumps({"action": "get_state"}) + "\n").encode())
                last_poll = now
            except OSError:
                break

def rotate_point(point, angle_x, angle_y):
    x, y, z = point
    cosy, siny = math.cos(angle_y), math.sin(angle_y)
    x, z = x * cosy - z * siny, x * siny + z * cosy
    cosx, sinx = math.cos(angle_x), math.sin(angle_x)
    y, z = y * cosx - z * sinx, y * sinx + z * cosx
    return x, y, z

def project_rotated(rx, ry, rz, distance=30, scale=4000):
    z = rz + distance
    if z < 0.5:
        z = 0.5
    factor = scale / z
    return rx * factor, ry * factor, z

def project(point, angle_x, angle_y, distance=30, scale=4000):
    rx, ry, rz = rotate_point(point, angle_x, angle_y)
    return project_rotated(rx, ry, rz, distance, scale)

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
TERRAIN_COLORS = {
    "Plains": (120, 170, 90),
    "Mountains": (120, 100, 90),
    "Canyon": (150, 110, 70),
    "Highlands": (100, 140, 80),
    "Crater Field": (130, 130, 130),
    "Impact Basin": (100, 100, 110),
    "Regolith Plains": (150, 140, 130),
    "Ridge": (110, 105, 100),
    "Lava Flow": (200, 60, 20),
    "Ash Plains": (80, 70, 70),
    "Basalt Rock": (50, 50, 55),
    "Caldera": (230, 90, 30),
    "Ice Sheet": (220, 235, 245),
    "Frozen Ridge": (180, 200, 220),
    "Crevasse": (140, 170, 200),
    "Snow Plains": (240, 245, 250),
    "Dunes": (210, 180, 120),
    "Rocky Flat": (170, 140, 100),
    "Mesa": (190, 120, 80),
    "Dry Basin": (160, 130, 90),
    "Open Water": (40, 90, 160),
    "Reef": (60, 140, 150),
    "Island": (180, 170, 90),
    "Deep Trench": (20, 50, 100),
    "Atmosphere": (200, 210, 230),
    "Storm Band": (150, 150, 180),
}

PLANET_SPHERE_RADIUS = 220  # render units for the sphere itself

def start_networking():
    global sock, sock_file
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    sock_file = sock.makefile('r')
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
    star_screen_positions = []
    latest_state = {"tick": 0, "you": {"resources": 0}}

    view_mode = "universe"
    current_system = None
    entering_system = False
    system_view_radius = 400.0  # render units; ~4 AU by default
    system_bodies_screen = []
    system_view_center = (0.0, 0.0)
    focused_body = None
    info_panel_open = False
    star_screen_pos = None

    system_estimate = None
    estimate_coords = None

    entering_planet = False
    current_planet_terrain = None
    planet_view_distance = 500.0  # smaller = zoomed in on the sphere

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN and event.key == pygame.K_b:
                outgoing.put({"action": "build", "params": {"cost": 10}})

            elif event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
                if view_mode == "planet":
                    view_mode = "system"
                    current_planet_terrain = None
                elif view_mode == "system":
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
                    system_view_radius = max(20.0, min(system_view_radius, 4000.0))
                elif view_mode == "planet":
                    planet_view_distance -= event.y * 30
                    planet_view_distance = max(230.0, min(planet_view_distance, 1500.0))

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
                            entering_system = True
                            outgoing.put({"action": "get_system", "params": {"coords": list(closest["coords"])}})
                        else:
                            view_center = closest["coords"]
                            system_estimate = None
                            estimate_coords = tuple(closest["coords"])
                            outgoing.put({"action": "get_system_estimate", "params": {"coords": list(closest["coords"])}})
                            outgoing.put({"action": "get_region", "params": {"center": list(closest["coords"]), "radius": 5}})

                elif view_mode == "system":
                    hit = None

                    if star_screen_pos:
                        d = math.hypot(mx - star_screen_pos[0], my - star_screen_pos[1])
                        if d < 20:
                            hit = {"kind": "star"}

                    if hit is None:
                        for sx, sy, planet in system_bodies_screen:
                            d = math.hypot(mx - sx, my - sy)
                            if d < 25:
                                angle_rad = math.radians(planet["angle_deg"])
                                orbit_units = planet["orbit_au"] * AU_SCALE
                                px = orbit_units * math.cos(angle_rad)
                                pz = orbit_units * math.sin(angle_rad)
                                hit = {"kind": "planet", "planet": planet, "pos": (px, pz)}
                                break

                    if hit:
                        is_same = (
                            focused_body is not None
                            and focused_body["kind"] == hit["kind"]
                            and (hit["kind"] == "star" or focused_body["planet"]["name"] == hit["planet"]["name"])
                        )

                        if info_panel_open and is_same and hit["kind"] == "planet":
                            entering_planet = True
                            outgoing.put({
                                "action": "get_planet_terrain",
                                "params": {
                                    "coords": list(current_system["coords"]),
                                    "planet_index": hit["planet"]["index"],
                                }
                            })
                        elif info_panel_open:
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
            elif msg.get("type") == "system_estimate":
                system_estimate = msg["data"]
            elif msg.get("type") == "planet_terrain":
                if entering_planet:
                    current_planet_terrain = msg["data"]
                    view_mode = "planet"
                    entering_planet = False

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

            if system_estimate and estimate_coords == tuple(view_center):
                panel_w = 340
                pygame.draw.rect(screen, (20, 20, 30), (0, 0, panel_w, screen.get_height()))
                pygame.draw.line(screen, (80, 80, 90), (panel_w, 0), (panel_w, screen.get_height()), 2)

                lo, hi = system_estimate["estimated_planet_range"]
                lines = [
                    f"Star type: {system_estimate['star_type']}",
                    f"Est. planetary bodies: ~{lo}-{hi}",
                    "",
                    "Sensor survey (estimate only):",
                ]
                for element, label in system_estimate["resource_estimate"].items():
                    lines.append(f"  {element}: {label}")

                y_offset = 20
                for line in lines:
                    text_surface = small_font.render(line, True, (230, 230, 230))
                    screen.blit(text_surface, (15, y_offset))
                    y_offset += 24

        elif view_mode == "system" and current_system:
            fx, fz = system_view_center
            SYSTEM_BASE_SCALE = 6000
            SYSTEM_BASE_RADIUS = 400.0
            scale_factor = SYSTEM_BASE_SCALE * (SYSTEM_BASE_RADIUS / system_view_radius)

            showing_star_panel = (
                info_panel_open and focused_body and focused_body["kind"] == "star"
            )

            if showing_star_panel:
                hz = current_system["habitable_zone"]
                if hz["outer"] > 0:
                    hz_inner_units = hz["inner"] * AU_SCALE
                    hz_outer_units = hz["outer"] * AU_SCALE
                    zone_surface = pygame.Surface((screen.get_width(), screen.get_height()), pygame.SRCALPHA)
                    ZONE_SEGMENTS = 48
                    outer_pts, inner_pts = [], []
                    for i in range(ZONE_SEGMENTS + 1):
                        theta = 2 * math.pi * i / ZONE_SEGMENTS
                        ox = hz_outer_units * math.cos(theta) - fx
                        oz = hz_outer_units * math.sin(theta) - fz
                        osx, osy, _ = project((ox, 0, oz), angle_x, angle_y, distance=600, scale=scale_factor)
                        outer_pts.append((center_x + osx, center_y + osy))

                        ix = hz_inner_units * math.cos(theta) - fx
                        iz = hz_inner_units * math.sin(theta) - fz
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
                orbit_units = planet["orbit_au"] * AU_SCALE
                ring_points = []
                for i in range(ORBIT_SEGMENTS + 1):
                    theta = 2 * math.pi * i / ORBIT_SEGMENTS
                    ox = orbit_units * math.cos(theta) - fx
                    oz = orbit_units * math.sin(theta) - fz
                    rsx, rsy, rsz = project((ox, 0, oz), angle_x, angle_y, distance=600, scale=scale_factor)
                    ring_points.append((center_x + rsx, center_y + rsy))
                pygame.draw.aalines(screen, (90, 90, 90), False, ring_points)

            projected = []
            for planet in current_system["planets"]:
                orbit_units = planet["orbit_au"] * AU_SCALE
                angle_rad = math.radians(planet["angle_deg"])
                px = orbit_units * math.cos(angle_rad) - fx
                pz = orbit_units * math.sin(angle_rad) - fz
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
                        f"Atmosphere: {'Yes' if planet['has_atmosphere'] else 'None'}",
                        f"Orbit: {planet['orbit_au']:.3f} AU",
                        f"Size: {planet['size']} km",
                        f"Rich deposit: {planet.get('rich_deposit', '-')}",
                        "",
                        "Resources (ppm):",
                    ]
                    for element, amount in sorted(planet["resources"].items(), key=lambda kv: -kv[1]):
                        lines.append(f"  {element}: {amount:,.6f}")
                    lines.append("")
                    lines.append("Click again to view surface")
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
                        f"  {hz['inner']:.3f}-{hz['outer']:.3f} AU" if hz["outer"] > 0 else "  None",
                    ]

                y_offset = 20
                for line in lines:
                    text_surface = small_font.render(line, True, (230, 230, 230))
                    screen.blit(text_surface, (panel_x + 15, y_offset))
                    y_offset += 26

        elif view_mode == "planet" and current_planet_terrain:
            grid = current_planet_terrain["grid"]
            grid_size = len(grid)

            title_surface = font.render(current_planet_terrain["planet_name"], True, (230, 230, 230))
            screen.blit(title_surface, (20, 15))

            SPHERE_SCALE = 6000
            SPHERE_BASE_DISTANCE = 500.0
            scale_factor = SPHERE_SCALE * (SPHERE_BASE_DISTANCE / planet_view_distance)

            def sphere_point(lat, lon):
                x = PLANET_SPHERE_RADIUS * math.cos(lat) * math.cos(lon)
                y = PLANET_SPHERE_RADIUS * math.sin(lat)
                z = PLANET_SPHERE_RADIUS * math.cos(lat) * math.sin(lon)
                return x, y, z

            tiles_to_draw = []  # (depth, [screen_points], color)

            for ty in range(grid_size):
                lat0_deg = -90 + ty / grid_size * 180
                lat1_deg = -90 + (ty + 1) / grid_size * 180
                lat_mid = math.radians((lat0_deg + lat1_deg) / 2)

                # Fewer, wider longitude tiles near the poles so every tile
                # covers roughly the same physical area on the sphere,
                # instead of cramming grid_size tiles into a shrinking ring.
                num_lon = max(1, round(grid_size * math.cos(lat_mid)))
                lon_width_deg = 360.0 / num_lon

                for j in range(num_lon):
                    lon0_deg = j * lon_width_deg
                    lon1_deg = (j + 1) * lon_width_deg
                    lon_mid_deg = (lon0_deg + lon1_deg) / 2

                    # Sample the underlying terrain data at this tile's center
                    tx = int((lon_mid_deg / 360.0) * grid_size) % grid_size
                    terrain = grid[tx][ty]

                    lat0, lat1 = math.radians(lat0_deg), math.radians(lat1_deg)
                    lon0, lon1 = math.radians(lon0_deg), math.radians(lon1_deg)

                    center_point = sphere_point(lat_mid, math.radians(lon_mid_deg))
                    _, _, center_rz = rotate_point(center_point, angle_x, angle_y)
                    if center_rz >= 0:
                        continue  # facing away from us

                    corners = [
                        sphere_point(lat0, lon0),
                        sphere_point(lat0, lon1),
                        sphere_point(lat1, lon1),
                        sphere_point(lat1, lon0),
                    ]

                    screen_points = []
                    for corner in corners:
                        rx, ry, rz = rotate_point(corner, angle_x, angle_y)
                        sx, sy, _ = project_rotated(rx, ry, rz, distance=planet_view_distance, scale=scale_factor)
                        screen_points.append((center_x + sx, center_y + sy))

                    color = TERRAIN_COLORS.get(terrain, (200, 200, 200))
                    tiles_to_draw.append((center_rz, screen_points, color))

            tiles_to_draw.sort(key=lambda t: -t[0])
            for depth, screen_points, color in tiles_to_draw:
                pygame.draw.polygon(screen, color, screen_points)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()