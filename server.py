import asyncio
import json
from universe import generate_system
from universe import generate_region
import db
# Authoritative game state
game_state = {
    "tick": 0
}

def validate_command(player_id, msg):
    if "action" not in msg:
        return False, "Missing 'action' field"

    action = msg["action"]
    if action not in ("build", "get_state", "hello", "get_system", "get_region"):
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

    if action == "get_system":
        coords = msg.get("params", {}).get("coords")
        if not (isinstance(coords, list) and len(coords) == 3 and all(isinstance(c, int) for c in coords)):
            return False, "coords must be a list of 3 integers"

    if action == "build":
        params = msg.get("params", {})
        cost = params.get("cost")
        if not isinstance(cost, (int, float)) or cost <= 0:
            return False, "Invalid or missing cost"
        # actual affordability check happens in handle_command (needs a DB read)

    return True, None

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    player_id = None  # will be set once client sends "hello"

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

            # First message from any client must be a "hello" with their name
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

            await handle_command(player_id, msg, writer)
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

    elif action == "get_region":
        center = tuple(msg["params"]["center"])
        radius = msg["params"]["radius"]
        stars = generate_region(center, radius)
        await send_json(writer, {"type": "region", "data": stars})

async def send_json(writer, obj):
    writer.write((json.dumps(obj) + "\n").encode())
    await writer.drain()

async def game_tick_loop():
    """Advances the simulation on its own — clients pull state, they don't get pushed to."""
    while True:
        game_state["tick"] += 1
        # e.g. run production, resource regen etc. here
        await asyncio.sleep(1)

async def main():
    db.init_db()
    server = await asyncio.start_server(handle_client, '127.0.0.1', 5555)
    asyncio.create_task(game_tick_loop())
    print("Server running on 127.0.0.1:5555")
    async with server:
        await server.serve_forever()

asyncio.run(main())