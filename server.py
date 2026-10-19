import asyncio
import json
from universe import generate_system, generate_region, estimate_system_resources, generate_planet_terrain
import db

game_state = {
    "tick": 0
}

def validate_command(player_id, msg):
    if "action" not in msg:
        return False, "Missing 'action' field"

    action = msg["action"]
    if action not in ("build", "get_state", "hello", "get_system", "get_region",
                      "get_system_estimate", "get_planet_terrain"):
        return False, f"Unknown action '{action}'"

    if action == "hello":
        if not msg.get("name"):
            return False, "hello requires a name"
        return True, None

    if player_id is None:
        return False, "Must send hello first"

    if action == "get_region":
        params = msg.get("params", {})
        center = params.get("center")
        radius = params.get("radius")
        if not (isinstance(center, list) and len(center) == 3):
            return False, "center must be [x, y, z]"
        if not isinstance(radius, int) or not (1 <= radius <= 8):
            return False, "radius must be an int between 1 and 8"

    if action in ("get_system", "get_system_estimate"):
        coords = msg.get("params", {}).get("coords")
        if not (isinstance(coords, list) and len(coords) == 3 and all(isinstance(c, int) for c in coords)):
            return False, "coords must be a list of 3 integers"

    if action == "get_planet_terrain":
        params = msg.get("params", {})
        coords = params.get("coords")
        planet_index = params.get("planet_index")
        if not (isinstance(coords, list) and len(coords) == 3 and all(isinstance(c, int) for c in coords)):
            return False, "coords must be a list of 3 integers"
        if not isinstance(planet_index, int) or planet_index < 0:
            return False, "planet_index must be a non-negative integer"

    if action == "build":
        params = msg.get("params", {})
        cost = params.get("cost")
        if not isinstance(cost, (int, float)) or cost <= 0:
            return False, "Invalid or missing cost"

    return True, None

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    player_id = None

    try:
        while True:
            data = await reader.readline()
            if not data:
                break
            try:
                msg = json.loads(data.decode())
            except json.JSONDecodeError:
                await send_json(writer, {"type": "error", "error": "Malformed JSON"})
                continue

            if player_id is None:
                if msg.get("action") != "hello" or not msg.get("name"):
                    await send_json(writer, {"type": "error", "error": "Must send hello with a name first"})
                    continue

                player_id = msg["name"]
                created = await asyncio.to_thread(db.get_or_create_player, player_id)
                if created:
                    print(f"New player '{player_id}' connected from {addr}")
                else:
                    print(f"'{player_id}' reconnected from {addr}")

                await send_json(writer, {"type": "hello_ack", "name": player_id})
                continue

            ok, error = validate_command(player_id, msg)
            if not ok:
                await send_json(writer, {"type": "error", "error": error})
                continue

            try:
                await handle_command(player_id, msg, writer)
            except Exception as e:
                print(f"Error handling command from '{player_id}': {e}")
                await send_json(writer, {"type": "error", "error": "Internal server error"})
    except (asyncio.IncompleteReadError, ConnectionResetError):
        pass
    finally:
        if player_id:
            print(f"'{player_id}' disconnected")
        writer.close()

async def handle_command(player_id, msg, writer):
    action = msg["action"]

    if action == "get_state":
        player_data = await asyncio.to_thread(db.get_player_state, player_id)
        await send_json(writer, {
            "type": "state",
            "data": {"tick": game_state["tick"], "you": player_data}
        })

    elif action == "build":
        cost = msg["params"]["cost"]
        ok, error = await asyncio.to_thread(db.try_spend_resources, player_id, cost)
        if not ok:
            await send_json(writer, {"type": "error", "error": error})
        else:
            await send_json(writer, {"type": "ack", "action": "build", "ok": True})

    elif action == "get_system":
        coords = tuple(msg["params"]["coords"])
        system = generate_system(coords)
        await send_json(writer, {"type": "system", "data": system})

    elif action == "get_system_estimate":
        coords = tuple(msg["params"]["coords"])
        estimate = estimate_system_resources(coords)
        await send_json(writer, {"type": "system_estimate", "data": estimate})

    elif action == "get_region":
        center = tuple(msg["params"]["center"])
        radius = msg["params"]["radius"]
        stars = generate_region(center, radius)
        await send_json(writer, {"type": "region", "data": stars})

    elif action == "get_planet_terrain":
        coords = tuple(msg["params"]["coords"])
        planet_index = msg["params"]["planet_index"]
        system = generate_system(coords)
        if planet_index >= len(system["planets"]):
            await send_json(writer, {"type": "error", "error": "Invalid planet_index"})
            return
        planet = system["planets"][planet_index]
        terrain = generate_planet_terrain(coords, planet_index, planet["type"], planet["has_atmosphere"])
        await send_json(writer, {
            "type": "planet_terrain",
            "data": {"planet_name": planet["name"], "planet_index": planet_index, "grid": terrain}
        })

async def send_json(writer, obj):
    writer.write((json.dumps(obj) + "\n").encode())
    await writer.drain()

async def game_tick_loop():
    while True:
        game_state["tick"] += 1
        await asyncio.sleep(1)

async def main():
    db.init_db()
    server = await asyncio.start_server(handle_client, '127.0.0.1', 5555)
    asyncio.create_task(game_tick_loop())
    print("Server running on 127.0.0.1:5555")
    async with server:
        await server.serve_forever()

asyncio.run(main())