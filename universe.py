import hashlib
import random

STAR_TYPES = ["Red Dwarf", "Yellow Star", "Blue Giant", "White Dwarf", "Neutron Star"]
PLANET_TYPES = ["Rocky", "Gas Giant", "Ice World", "Volcanic", "Ocean", "Desert"]
RESOURCES = ["Iron", "Titanium", "Helium-3", "Water Ice", "Silicon", "Rare Crystals"]

STAR_DATA = {
    "Red Dwarf":    {"temp_k": (2300, 3900),      "mass_msun": (0.08, 0.45)},
    "Yellow Star":  {"temp_k": (5300, 6000),      "mass_msun": (0.8, 1.04)},
    "Blue Giant":   {"temp_k": (10000, 33000),    "mass_msun": (2.1, 16)},
    "White Dwarf":  {"temp_k": (8000, 40000),     "mass_msun": (0.5, 1.4)},
    "Neutron Star": {"temp_k": (600000, 1000000), "mass_msun": (1.4, 2.2)},
}

STAR_HABITABLE_ZONE = {
    "Red Dwarf":    (20, 45),
    "Yellow Star":  (150, 260),
    "Blue Giant":   (650, 950),
    "White Dwarf":  (5, 15),
    "Neutron Star": (0, 0),
}

ATMOSPHERE_CHANCE = {
    "Rocky": 0.25,
    "Volcanic": 0.4,
    "Ice World": 0.5,
    "Desert": 0.6,
    "Ocean": 0.9,
    "Gas Giant": 1.0,
}

# Rocky worlds branch on atmosphere (craters vs. eroded terrain); other
# types don't need that distinction for now.
TERRAIN_BY_PLANET_TYPE = {
    "Rocky": {
        True:  ["Plains", "Mountains", "Canyon", "Highlands"],
        False: ["Crater Field", "Impact Basin", "Regolith Plains", "Ridge"],
    },
    "Volcanic": ["Lava Flow", "Ash Plains", "Basalt Rock", "Caldera"],
    "Ice World": ["Ice Sheet", "Frozen Ridge", "Crevasse", "Snow Plains"],
    "Desert": ["Dunes", "Rocky Flat", "Mesa", "Dry Basin"],
    "Ocean": ["Open Water", "Reef", "Island", "Deep Trench"],
}

PLANET_GRID_SIZE = 40

RESOURCE_ESTIMATE_LABELS = [
    (0, "Not detected"),
    (0.01, "Trace amounts"),
    (0.5, "Present"),
    (2, "Significant deposits"),
    (10, "Rich deposits likely"),
]


def _seed_for(coords):
    """
    Turn any-length coordinate tuple into a deterministic integer seed.
    Same input -> same seed, every time.
    """
    key = ":".join(str(c) for c in coords)
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest[:16], 16)

<<<<<<< Updated upstream
=======

def generate_planet_resources(coords):
    """
    Every planet has a little of everything, weighted by real crustal
    abundance, plus one randomly-rolled 'rich deposit' element that's
    unusually concentrated there.
    """
    rng = random.Random(_seed_for((*coords, "resources")))
    resources = {}
    for element, base_abundance in RESOURCE_ABUNDANCE.items():
        variance = rng.uniform(0.4, 1.6)
        resources[element] = round(base_abundance * variance, 6)

    rich_element = rng.choice(list(RESOURCE_ABUNDANCE.keys()))
    boost = rng.uniform(20, 100)
    resources[rich_element] = round(resources[rich_element] * boost, 6)

    return resources, rich_element


>>>>>>> Stashed changes
def generate_system(coords):
    """
    Deterministically generate a star system at the given (x, y, z) coordinate.
    Calling this twice with the same coords always returns the same system.
    """
    seed = _seed_for(coords)
    rng = random.Random(seed)

    star_type = rng.choice(STAR_TYPES)
    num_planets = rng.randint(0, 8)

    planets = []
    for i in range(num_planets):
        planet_seed_coords = (coords[0], coords[1], coords[2], i)  # unique per planet
        planet_rng = random.Random(_seed_for(planet_seed_coords))
        resources, rich_element = generate_planet_resources(planet_seed_coords)

<<<<<<< Updated upstream
        planets.append({
            "name": f"{coords[0]}-{coords[1]}-{coords[2]}-P{i+1}",
            "type": planet_rng.choice(PLANET_TYPES),
            "resources": planet_rng.sample(RESOURCES, k=planet_rng.randint(1, 3)),
            "size": planet_rng.randint(1000, 20000),  # arbitrary unit, e.g. km radius
        })
=======
        ptype = planet_rng.choice(PLANET_TYPES)
        has_atmosphere = planet_rng.random() < ATMOSPHERE_CHANCE.get(ptype, 0.3)

        planets.append({
            "name": f"{coords[0]}-{coords[1]}-{coords[2]}-P{i+1}",
            "index": i,
            "type": ptype,
            "has_atmosphere": has_atmosphere,
            "resources": resources,
            "rich_deposit": rich_element,
            "size": planet_rng.randint(1000, 20000),
            "orbit_radius": 80 + i * 60 + planet_rng.uniform(-20, 20),
            "angle_deg": planet_rng.uniform(0, 360),
        })

    hz_inner, hz_outer = STAR_HABITABLE_ZONE.get(star_type, (0, 0))
    star_info = STAR_DATA.get(star_type, {})
>>>>>>> Stashed changes

    return {
        "coords": coords,
        "star_type": star_type,
        "planets": planets,
    }
<<<<<<< Updated upstream
def star_exists(coords, chance=0.75):
=======


def _label_for_ratio(ratio):
    label = RESOURCE_ESTIMATE_LABELS[0][1]
    for threshold, text in RESOURCE_ESTIMATE_LABELS:
        if ratio >= threshold:
            label = text
    return label


def estimate_system_resources(coords):
    """
    A rough, sensor-based survey estimate — like real spectroscopy, this
    gives qualitative likelihoods, not exact quantities. The estimated
    planet count is a fuzzed range, not the precise number — you only
    get exact data once you actually travel there.
    """
    full_system = generate_system(coords)
    planets = full_system["planets"]

    aggregate = {}
    for element, base in RESOURCE_ABUNDANCE.items():
        if planets:
            avg = sum(p["resources"].get(element, 0) for p in planets) / len(planets)
        else:
            avg = 0
        ratio = (avg / base) if base else 0
        aggregate[element] = _label_for_ratio(ratio)

    est_rng = random.Random(_seed_for((*coords, "estimate")))
    real_count = len(planets)
    fuzz = est_rng.randint(-1, 1)
    est_low = max(0, real_count + fuzz - est_rng.randint(0, 1))
    est_high = real_count + fuzz + est_rng.randint(0, 1)

    return {
        "star_type": full_system["star_type"],
        "estimated_planet_range": [est_low, est_high],
        "resource_estimate": aggregate,
    }


def generate_planet_terrain(system_coords, planet_index, planet_type, has_atmosphere):
    """
    Deterministic 2D terrain grid for a single planet. Gas giants have
    no solid ground — tiles are mostly open sky with rare floating
    'Cloud City' platforms instead of natural terrain features.
    """
    terrain_entry = TERRAIN_BY_PLANET_TYPE.get(planet_type)
    if isinstance(terrain_entry, dict):
        terrain_options = terrain_entry.get(has_atmosphere, list(terrain_entry.values())[0])
    else:
        terrain_options = terrain_entry

    grid = []
    for tx in range(PLANET_GRID_SIZE):
        row = []
        for ty in range(PLANET_GRID_SIZE):
            tile_seed = (*system_coords, planet_index, tx, ty, "terrain")
            rng = random.Random(_seed_for(tile_seed))

            if planet_type == "Gas Giant":
                roll = rng.random()
                if roll < 0.12:
                    terrain = "Storm Band"
                else:
                    terrain = "Atmosphere"
            else:
                terrain = rng.choice(terrain_options)
            row.append(terrain)
        grid.append(row)
    return grid


def star_exists(coords, chance=0.075):
>>>>>>> Stashed changes
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