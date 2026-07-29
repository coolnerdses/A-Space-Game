"""
db.py — persistence layer for A Space Game.

Uses SQLAlchemy so the underlying database can be swapped later
(SQLite now for zero-setup local dev -> PostgreSQL when this needs
to handle many concurrent players) by changing only DATABASE_URL.
Nothing else in this file, or in server.py, needs to change to make
that move later.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    create_engine, ForeignKey, String, Integer, Float, Boolean, JSON, DateTime, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATABASE_URL = "sqlite:///game.db"
# To move to Postgres later, this becomes something like:
# DATABASE_URL = "postgresql+psycopg2://user:password@host:5432/dbname"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def now_utc():
    return datetime.now(timezone.utc)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    resources: Mapped[float] = mapped_column(Float, default=100.0)
    wanted_level: Mapped[int] = mapped_column(Integer, default=0)
    corporation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("corporations.id"), nullable=True)
    corporation_role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    last_login: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    corporation: Mapped[Optional["Corporation"]] = relationship(
        back_populates="members",
        foreign_keys=[corporation_id],
    )


class Corporation(Base):
    __tablename__ = "corporations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    founder_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    members: Mapped[list["Player"]] = relationship(
        back_populates="corporation",
        foreign_keys="Player.corporation_id",
    )


class Ship(Base):
    __tablename__ = "ships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    owner_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    owner_corporation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("corporations.id"), nullable=True)
    components: Mapped[dict] = mapped_column(JSON, default=dict)  # modular parts — shape TBD by ship design
    coords_x: Mapped[float] = mapped_column(Float, default=0.0)
    coords_y: Mapped[float] = mapped_column(Float, default=0.0)
    coords_z: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | destroyed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class StarSystem(Base):
    """
    Only systems that have actually been touched (discovered, or connected
    by a lane) get a row — the universe itself stays procedurally generated
    from coordinates and is never stored wholesale.
    """
    __tablename__ = "star_systems"
    __table_args__ = (UniqueConstraint("x", "y", "z", name="uq_system_coords"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
    z: Mapped[int] = mapped_column(Integer)
    discovered_by_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    discovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_core: Mapped[bool] = mapped_column(Boolean, default=False)  # dynamic safe-space flag


class Planet(Base):
    """Only stores a row once something changes from the generated baseline."""
    __tablename__ = "planets"
    __table_args__ = (UniqueConstraint("system_x", "system_y", "system_z", "planet_index", name="uq_planet"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    system_x: Mapped[int] = mapped_column(Integer)
    system_y: Mapped[int] = mapped_column(Integer)
    system_z: Mapped[int] = mapped_column(Integer)
    planet_index: Mapped[int] = mapped_column(Integer)
    resource_overrides: Mapped[dict] = mapped_column(JSON, default=dict)  # depletion vs. generated baseline
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class PlanetTile(Base):
    """A single ownable plot. Only claimed tiles get a row — the grid itself isn't stored empty."""
    __tablename__ = "planet_tiles"
    __table_args__ = (
        UniqueConstraint("system_x", "system_y", "system_z", "planet_index", "tile_index", name="uq_tile"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    system_x: Mapped[int] = mapped_column(Integer)
    system_y: Mapped[int] = mapped_column(Integer)
    system_z: Mapped[int] = mapped_column(Integer)
    planet_index: Mapped[int] = mapped_column(Integer)
    tile_index: Mapped[int] = mapped_column(Integer)
    owner_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    owner_corporation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("corporations.id"), nullable=True)
    for_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    asking_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tile_id: Mapped[int] = mapped_column(ForeignKey("planet_tiles.id"))
    building_type: Mapped[str] = mapped_column(String(64))
    recipe: Mapped[dict] = mapped_column(JSON, default=dict)     # {"inputs": {...}, "outputs": {...}}
    storage: Mapped[dict] = mapped_column(JSON, default=dict)    # currently stored resources
    last_tick_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class JumpLane(Base):
    __tablename__ = "jump_lanes"
    __table_args__ = (
        UniqueConstraint("from_x", "from_y", "from_z", "to_x", "to_y", "to_z", name="uq_lane"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_x: Mapped[int] = mapped_column(Integer)
    from_y: Mapped[int] = mapped_column(Integer)
    from_z: Mapped[int] = mapped_column(Integer)
    to_x: Mapped[int] = mapped_column(Integer)
    to_y: Mapped[int] = mapped_column(Integer)
    to_z: Mapped[int] = mapped_column(Integer)
    owner_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    owner_corporation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("corporations.id"), nullable=True)
    travel_time_seconds: Mapped[float] = mapped_column(Float)  # shrinks as the lane gets refined
    toll_price: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class RouteKey(Base):
    """One-time-use quantum route data pass — the no-cloning toll mechanic."""
    __tablename__ = "route_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lane_id: Mapped[int] = mapped_column(ForeignKey("jump_lanes.id"))
    issued_to_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class MarketOrder(Base):
    __tablename__ = "market_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    system_x: Mapped[int] = mapped_column(Integer)
    system_y: Mapped[int] = mapped_column(Integer)
    system_z: Mapped[int] = mapped_column(Integer)
    resource: Mapped[str] = mapped_column(String(64))
    order_type: Mapped[str] = mapped_column(String(4))  # "buy" | "sell"
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    corporation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("corporations.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class LedgerEntry(Base):
    """
    Append-only transaction log — rows are only ever added, never edited
    or deleted. This is the auditable-ledger approach discussed instead
    of an actual blockchain: it gives the same 'can't fake your balance'
    trust property without distributed-consensus overhead, since the
    server is already the trusted authority.
    """
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    from_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    to_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(32), default="credits")
    reason: Mapped[str] = mapped_column(String(64))  # "trade", "toll", "build_cost", etc.


def init_db():
    Base.metadata.create_all(engine)


# --- Player operations used by server.py ---

def get_or_create_player(name: str) -> bool:
    """Returns True if a new player row was created, False if one already existed."""
    with SessionLocal() as session:
        player = session.query(Player).filter_by(name=name).first()
        if player is None:
            session.add(Player(name=name))
            session.commit()
            return True
        player.last_login = now_utc()
        session.commit()
        return False


def get_player_state(name: str) -> dict:
    with SessionLocal() as session:
        player = session.query(Player).filter_by(name=name).first()
        if player is None:
            return {"resources": 0, "wanted_level": 0}
        return {"resources": player.resources, "wanted_level": player.wanted_level}


def try_spend_resources(name: str, amount: float):
    """Atomically checks and deducts resources, logging the spend to the ledger."""
    with SessionLocal() as session:
        player = session.query(Player).filter_by(name=name).first()
        if player is None:
            return False, "Unknown player"
        if player.resources < amount:
            return False, "Not enough resources"
        player.resources -= amount
        session.add(LedgerEntry(
            from_player_id=player.id,
            to_player_id=None,
            amount=amount,
            reason="build_cost",
        ))
        session.commit()
        return True, None