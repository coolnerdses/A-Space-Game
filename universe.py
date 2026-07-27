import hashlib
import random

# A few flavor pools to pick from — expand these later once you have your spec
STAR_TYPES = ["Red Dwarf", "Yellow Star", "Blue Giant", "White Dwarf", "Neutron Star"]
PLANET_TYPES = ["Rocky", "Gas Giant", "Ice World", "Volcanic", "Ocean", "Desert"]
RESOURCES = ["Iron", "Titanium", "Helium-3", "Water Ice", "Silicon", "Rare Crystals"]

def _seed_for(coords):
    """
    Turn any-length coordinate tuple into a deterministic integer seed.
    Same input -> same seed, every time.
    """
    key = ":".join(str(c) for c in coords)
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest[:16], 16)

def generate_system(coords):
    """
    Deterministically generate a star system at the given (x, y, z) coordinate.
    Calling this twice with the same coords always returns the same system.
    """
    seed = _seed_for(coords)
    rng = random.Random(seed)  # local RNG, doesn't touch global random state

    star_type = rng.choice(STAR_TYPES)
    num_planets = rng.randint(0, 8)

    planets = []
    for i in range(num_planets):
        planet_seed_coords = (coords[0], coords[1], coords[2], i)  # unique per planet
        planet_rng = random.Random(_seed_for(planet_seed_coords))

        planets.append({
            "name": f"{coords[0]}-{coords[1]}-{coords[2]}-P{i+1}",
            "type": planet_rng.choice(PLANET_TYPES),
            "resources": planet_rng.sample(RESOURCES, k=planet_rng.randint(1, 3)),
            "size": planet_rng.randint(1000, 20000),  # arbitrary unit, e.g. km radius
        })

    return {
        "coords": coords,
        "star_type": star_type,
        "planets": planets,
    }
def star_exists(coords, chance=0.75):
    """
    Deterministic yes/no: does a star exist at this coordinate?
    Same coords always give the same answer.
    """
    seed = _seed_for(coords)
    rng = random.Random(seed)
    return rng.random() < chance

def generate_region(center, radius):
    """
    Scan a cube of coordinates around center, return only cells that
    actually have a star. Lightweight (no planets) — just enough for a map view.
    """
    cx, cy, cz = center
    stars = []
    for x in range(cx - radius, cx + radius + 1):
        for y in range(cy - radius, cy + radius + 1):
            for z in range(cz - radius, cz + radius + 1):
                coords = (x, y, z)
                if star_exists(coords):
                    seed = _seed_for(coords)
                    rng = random.Random(seed)
                    stars.append({
                        "coords": coords,
                        "star_type": rng.choice(STAR_TYPES),
                    })
    return stars