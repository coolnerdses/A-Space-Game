import hashlib
import random

STAR_TYPES = ["Red Dwarf", "Yellow Star", "Blue Giant", "White Dwarf", "Neutron Star"]
PLANET_TYPES = ["Rocky", "Gas Giant", "Ice World", "Volcanic", "Ocean", "Desert"]

RESOURCE_ABUNDANCE = {
    "Oxygen": 460000,
    "Silicon": 282000,
    "Aluminum": 82000,
    "Iron": 56000,
    "Calcium": 42000,
    "Sodium": 23000,
    "Magnesium": 23000,
    "Potassium": 21000,
    "Titanium": 5700,
    "Hydrogen": 1400,
    "Carbon": 200,
    "Nickel": 84,
    "Zinc": 70,
    "Copper": 60,
    "Cobalt": 25,
    "Lead": 14,
    "Tin": 2.3,
    "Silver": 0.075,
    "Platinum": 0.005,
    "Gold": 0.004,
}

STAR_DATA = {
    "Red Dwarf":    {"temp_k": (2300, 3900),      "mass_msun": (0.08, 0.45)},
    "Yellow Star":  {"temp_k": (5300, 6000),      "mass_msun": (0.8, 1.04)},
    "Blue Giant":   {"temp_k": (10000, 33000),    "mass_msun": (2.1, 16)},
    "White Dwarf":  {"temp_k": (8000, 40000),     "mass_msun": (0.5, 1.4)},
    "Neutron Star": {"temp_k": (600000, 1000000), "mass_msun": (1.4, 2.2)},
}

# Habitable zone, in real astronomical units (AU). Scales with a star's
# luminosity — cooler/dimmer stars pull it in close, hotter/brighter
# stars push it far out. Sun's real HZ is roughly 0.95-1.4 AU.
STAR_HABITABLE_ZONE = {
    "Red Dwarf":    (0.05, 0.4),
    "Yellow Star":  (0.95, 1.4),
    "Blue Giant":   (20.0, 100.0),
    "White Dwarf":  (0.005, 0.02),
    "Neutron Star": (0.0, 0.0),
}

ATMOSPHERE_CHANCE = {
    "Rocky": 0.25,
    "Volcanic": 0.4,
    "Ice World": 0.5,
    "Desert": 0.6,
    "Ocean": 0.9,
    "Gas Giant": 1.0,
}

# Realistic-ish orbital distance range per planet type, in AU. Rocky/
# volcanic/desert/ocean worlds cluster close to the star (like the
# terrestrial planets); ice worlds and gas giants spawn much farther
# out (like the outer solar system).
ORBIT_AU_RANGES = {
    "Rocky": (0.3, 2.2),
    "Volcanic": (0.2, 1.8),
    "Desert": (0.5, 2.5),
    "Ocean": (0.7, 2.8),
    "Ice World": (2.5, 15.0),
    "Gas Giant": (4.0, 30.0),
}

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
    key = ":".join(str(c) for c in coords)
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest[:16], 16)


def generate_planet_resources(coords):
    rng = random.Random(_seed_for((*coords, "resources")))
    resources = {}
    for element, base_abundance in RESOURCE_ABUNDANCE.items():
        variance = rng.uniform(0.4, 1.6)
        resources[element] = round(base_abundance * variance, 6)

    rich_element = rng.choice(list(RESOURCE_ABUNDANCE.keys()))
    boost = rng.uniform(20, 100)
    resources[rich_element] = round(resources[rich_element] * boost, 6)

    return resources, rich_element


def generate_system(coords):
    seed = _seed_for(coords)
    rng = random.Random(seed)

    star_type = rng.choice(STAR_TYPES)
    num_planets = rng.randint(0, 8)

    planets = []
    for i in range(num_planets):
        planet_seed_coords = (coords[0], coords[1], coords[2], i)
        planet_rng = random.Random(_seed_for(planet_seed_coords))
        resources, rich_element = generate_planet_resources(planet_seed_coords)

        ptype = planet_rng.choice(PLANET_TYPES)
        has_atmosphere = planet_rng.random() < ATMOSPHERE_CHANCE.get(ptype, 0.3)
        lo_au, hi_au = ORBIT_AU_RANGES.get(ptype, (0.3, 10.0))
        orbit_au = planet_rng.uniform(lo_au, hi_au)

        planets.append({
            "type": ptype,
            "has_atmosphere": has_atmosphere,
            "resources": resources,
            "rich_deposit": rich_element,
            "size": planet_rng.randint(1000, 20000),
            "orbit_au": orbit_au,
            "angle_deg": planet_rng.uniform(0, 360),
        })

    # Order planets by distance from the star, like a real solar system
    # (innermost first), and assign stable names/indices to match.
    planets.sort(key=lambda p: p["orbit_au"])
    for new_index, planet in enumerate(planets):
        planet["index"] = new_index
        planet["name"] = f"{coords[0]}-{coords[1]}-{coords[2]}-P{new_index+1}"

    hz_inner, hz_outer = STAR_HABITABLE_ZONE.get(star_type, (0, 0))
    star_info = STAR_DATA.get(star_type, {})

    return {
        "coords": coords,
        "star_type": star_type,
        "star_temp_k": star_info.get("temp_k", (0, 0)),
        "star_mass_msun": star_info.get("mass_msun", (0, 0)),
        "habitable_zone": {"inner": hz_inner, "outer": hz_outer},  # in AU
        "planets": planets,
    }


def _label_for_ratio(ratio):
    label = RESOURCE_ESTIMATE_LABELS[0][1]
    for threshold, text in RESOURCE_ESTIMATE_LABELS:
        if ratio >= threshold:
            label = text
    return label


def estimate_system_resources(coords):
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
    seed = _seed_for(coords)
    rng = random.Random(seed)
    return rng.random() < chance


def generate_region(center, radius):
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