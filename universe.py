import hashlib
import random

# A few flavor pools to pick from — expand these later once you have your spec
STAR_TYPES = ["Red Dwarf", "Yellow Star", "Blue Giant", "White Dwarf", "Neutron Star"]
STAR_DATA = {
    "Red Dwarf":    {"temp_k": (2300, 3900),  "mass_msun": (0.08, 0.45)},
    "Yellow Star":  {"temp_k": (5300, 6000),  "mass_msun": (0.8, 1.04)},
    "Blue Giant":   {"temp_k": (10000, 33000),"mass_msun": (2.1, 16)},
    "White Dwarf":  {"temp_k": (8000, 40000), "mass_msun": (0.5, 1.4)},
    "Neutron Star": {"temp_k": (600000, 1000000), "mass_msun": (1.4, 2.2)},
}

# Habitable zone expressed in the same abstract orbit_radius units your
# planets already use. Cooler/dimmer stars = zone pulled in close;
# hotter/brighter = pushed far out. Not literal AU, but relative ordering
# matches real astrophysics.
STAR_HABITABLE_ZONE = {
    "Red Dwarf":    (20, 45),
    "Yellow Star":  (150, 260),
    "Blue Giant":   (650, 950),
    "White Dwarf":  (5, 15),
    "Neutron Star": (0, 0),  # no meaningful habitable zone
}
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

def _seed_for(coords):
    """
    Turn any-length coordinate tuple into a deterministic integer seed.
    Same input -> same seed, every time.
    """
    key = ":".join(str(c) for c in coords)
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest[:16], 16)

def generate_planet_resources(coords):
    """
    Every planet has a little of everything, weighted by real crustal
    abundance, plus one randomly-rolled 'rich deposit' element that's
    unusually concentrated there.
    """
    rng = random.Random(_seed_for((*coords, "resources")))
    resources = {}
    for element, base_abundance in RESOURCE_ABUNDANCE.items():
        variance = rng.uniform(0.4, 1.6)  # natural planet-to-planet variance
        resources[element] = round(base_abundance * variance, 4)

    rich_element = rng.choice(list(RESOURCE_ABUNDANCE.keys()))
    boost = rng.uniform(20, 100)  # a real ore-grade deposit
    resources[rich_element] = round(resources[rich_element] * boost, 4)

    return resources, rich_element

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
        planet_seed_coords = (coords[0], coords[1], coords[2], i)
        planet_rng = random.Random(_seed_for(planet_seed_coords))

        planet_coords = (coords[0], coords[1], coords[2], i)
        resources, rich_element = generate_planet_resources(planet_coords)

        planets.append({
            "name": f"{coords[0]}-{coords[1]}-{coords[2]}-P{i+1}",
            "type": planet_rng.choice(PLANET_TYPES),
            "resources": resources,
            "rich_deposit": rich_element,
            "size": planet_rng.randint(1000, 20000),
            "orbit_radius": 80 + i * 60 + planet_rng.uniform(-20, 20),
            "angle_deg": planet_rng.uniform(0, 360),
        })
    hz_inner, hz_outer = STAR_HABITABLE_ZONE.get(star_type, (0, 0))
    star_info = STAR_DATA.get(star_type, {})

    return {
        "coords": coords,
        "star_type": star_type,
        "star_temp_k": star_info.get("temp_k", (0, 0)),
        "star_mass_msun": star_info.get("mass_msun", (0, 0)),
        "habitable_zone": {"inner": hz_inner, "outer": hz_outer},
        "planets": planets,
    }
def star_exists(coords, chance=0.075):
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