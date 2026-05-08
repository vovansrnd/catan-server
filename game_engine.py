"""
Колонизаторы: Terra Incognita — Игровой движок
"""

import math
import random
import secrets
import string
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Resource(Enum):
    WOOD = "wood"
    BRICK = "brick"
    WHEAT = "wheat"
    SHEEP = "sheep"
    ORE = "ore"
    NONE = "none"


class TerrainType(Enum):
    FOREST = "forest"
    HILLS = "hills"
    FIELDS = "fields"
    PASTURE = "pasture"
    MOUNTAINS = "mountains"
    DESERT = "desert"
    RUINS = "ruins"


TERRAIN_TO_RESOURCE = {
    TerrainType.FOREST: Resource.WOOD,
    TerrainType.HILLS: Resource.BRICK,
    TerrainType.FIELDS: Resource.WHEAT,
    TerrainType.PASTURE: Resource.SHEEP,
    TerrainType.MOUNTAINS: Resource.ORE,
    TerrainType.DESERT: Resource.NONE,
    TerrainType.RUINS: Resource.NONE,
}

TERRAIN_EMOJI = {
    TerrainType.FOREST: "🌲",
    TerrainType.HILLS: "🧱",
    TerrainType.FIELDS: "🌾",
    TerrainType.PASTURE: "🐑",
    TerrainType.MOUNTAINS: "⛏️",
    TerrainType.DESERT: "🏜️",
    TerrainType.RUINS: "🏛️",
}


class BuildingType(Enum):
    SETTLEMENT = "settlement"
    CITY = "city"


class DevCardType(Enum):
    KNIGHT = "knight"
    VICTORY_POINT = "victory_point"
    ROAD_BUILDING = "road_building"
    YEAR_OF_PLENTY = "year_of_plenty"
    MONOPOLY = "monopoly"
    EXPLORER = "explorer"
    PIRATE_HUNTER = "pirate_hunter"
    ANCIENT_MAP = "ancient_map"
    REBELLION = "rebellion"
    TRADE_AGREEMENT = "trade_agreement"
    SANCTIONS = "sanctions"


class DiscoveryType(Enum):
    TREASURE = "treasure"
    ANCIENT_KNOWLEDGE = "ancient_knowledge"
    CURSE = "curse"
    FERTILE_LAND = "fertile_land"
    FORTIFICATION = "fortification"
    LOST_TRIBE = "lost_tribe"


DISCOVERY_NAMES = {
    DiscoveryType.TREASURE: "💰 Сокровище",
    DiscoveryType.ANCIENT_KNOWLEDGE: "📜 Древнее знание",
    DiscoveryType.CURSE: "💀 Проклятие",
    DiscoveryType.FERTILE_LAND: "🌿 Плодородная земля",
    DiscoveryType.FORTIFICATION: "🏰 Укрепление",
    DiscoveryType.LOST_TRIBE: "👥 Потерянное племя",
}

DEV_CARD_NAMES = {
    DevCardType.KNIGHT: "⚔️ Рыцарь",
    DevCardType.VICTORY_POINT: "⭐ Победное очко",
    DevCardType.ROAD_BUILDING: "🛤️ Строительство дорог",
    DevCardType.YEAR_OF_PLENTY: "🌽 Год изобилия",
    DevCardType.MONOPOLY: "💰 Монополия",
    DevCardType.EXPLORER: "🧭 Исследователь",
    DevCardType.PIRATE_HUNTER: "🏹 Охотник на пиратов",
    DevCardType.ANCIENT_MAP: "🗺️ Древняя карта",
    DevCardType.REBELLION: "🔥 Восстание",
    DevCardType.TRADE_AGREEMENT: "🤝 Торговое соглашение",
    DevCardType.SANCTIONS: "🛑 Санкции",
}

COST_ROAD = {Resource.WOOD: 1, Resource.BRICK: 1}
COST_SETTLEMENT = {
    Resource.WOOD: 1,
    Resource.BRICK: 1,
    Resource.WHEAT: 1,
    Resource.SHEEP: 1,
}
COST_CITY = {Resource.WHEAT: 2, Resource.ORE: 3}
COST_DEV_CARD = {Resource.WHEAT: 1, Resource.SHEEP: 1, Resource.ORE: 1}


@dataclass
class HexTile:
    hex_id: int
    q: int
    r: int
    terrain: TerrainType
    number_token: int = 0
    has_pirate: bool = False
    discovery: Optional[DiscoveryType] = None
    fertility_bonus: bool = False

    @property
    def resource(self) -> Resource:
        return TERRAIN_TO_RESOURCE[self.terrain]

    def to_dict(self, revealed: bool = True):
        if not revealed:
            return {
                "hex_id": self.hex_id,
                "q": self.q,
                "r": self.r,
                "terrain": "unknown",
                "number_token": 0,
                "has_pirate": False,
                "has_ruins": False,
                "fertility_bonus": False,
                "revealed": False,
            }
        return {
            "hex_id": self.hex_id,
            "q": self.q,
            "r": self.r,
            "terrain": self.terrain.value,
            "number_token": self.number_token,
            "has_pirate": self.has_pirate,
            "has_ruins": self.terrain == TerrainType.RUINS,
            "fertility_bonus": self.fertility_bonus,
            "revealed": True,
        }


@dataclass
class Vertex:
    vertex_id: int
    x: float = 0.0
    y: float = 0.0
    adjacent_hexes: list = field(default_factory=list)
    adjacent_vertices: list = field(default_factory=list)
    adjacent_edges: list = field(default_factory=list)
    building_type: Optional[BuildingType] = None
    building_owner: Optional[int] = None
    is_port: bool = False
    port_type: Optional[Resource] = None

    @property
    def is_empty(self) -> bool:
        return self.building_type is None

    def to_dict(self):
        return {
            "vertex_id": self.vertex_id,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "building_type": self.building_type.value if self.building_type else None,
            "building_owner": self.building_owner,
            "is_port": self.is_port,
            "port_type": self.port_type.value if self.port_type else None,
        }


@dataclass
class Edge:
    edge_id: int
    vertices: tuple = (0, 0)
    adjacent_hexes: list = field(default_factory=list)
    road_owner: Optional[int] = None

    @property
    def is_empty(self) -> bool:
        return self.road_owner is None

    def to_dict(self):
        return {
            "edge_id": self.edge_id,
            "vertices": list(self.vertices),
            "road_owner": self.road_owner,
        }


@dataclass
class DevCardInstance:
    card_type: DevCardType
    bought_turn: int
    playable_from_turn: int

    def to_dict(self, current_turn: int):
        return {
            "type": self.card_type.value,
            "playable": current_turn >= self.playable_from_turn
            and self.card_type != DevCardType.VICTORY_POINT,
            "bought_turn": self.bought_turn,
            "playable_from_turn": self.playable_from_turn,
        }


@dataclass
class Player:
    player_id: int
    name: str
    color: str
    resources: dict = field(
        default_factory=lambda: {
            Resource.WOOD: 0,
            Resource.BRICK: 0,
            Resource.WHEAT: 0,
            Resource.SHEEP: 0,
            Resource.ORE: 0,
        }
    )
    dev_cards: list = field(default_factory=list)
    knights_played: int = 0
    victory_points_hidden: int = 0
    has_fortification: bool = False
    settlements_left: int = 5
    cities_left: int = 4
    roads_left: int = 15
    revealed_hexes: set = field(default_factory=set)
    dev_card_played_this_turn: bool = False
    connected: bool = False
    free_roads_pending: int = 0
    role_name: str = ""
    sanctioned_until_turn: int = -1
    trade_agreement_turn: int = -1

    # БЕЗОПАСНОСТЬ: используем secrets вместо uuid
    reconnect_token: str = field(
        default_factory=lambda: "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(32)
        )
    )

    @property
    def total_resources(self) -> int:
        return sum(self.resources.values())

    def has_resources(self, cost: dict) -> bool:
        return all(self.resources.get(r, 0) >= amt for r, amt in cost.items())

    def pay_resources(self, cost: dict) -> bool:
        if not self.has_resources(cost):
            return False
        for r, amt in cost.items():
            self.resources[r] -= amt
        return True

    def add_resource(self, resource: Resource, amount: int = 1):
        if resource != Resource.NONE:
            self.resources[resource] = self.resources.get(resource, 0) + amount

    def to_dict_private(self, current_turn: int):
        return {
            "player_id": self.player_id,
            "name": self.name,
            "color": self.color,
            "resources": {r.value: amt for r, amt in self.resources.items()},
            "dev_cards": [c.to_dict(current_turn) for c in self.dev_cards],
            "knights_played": self.knights_played,
            "settlements_left": self.settlements_left,
            "cities_left": self.cities_left,
            "roads_left": self.roads_left,
            "has_fortification": self.has_fortification,
            "total_resources": self.total_resources,
            "connected": self.connected,
            "free_roads_pending": self.free_roads_pending,
        }

    def to_dict_public(self):
        return {
            "player_id": self.player_id,
            "name": self.name,
            "role_name": self.role_name,
            "color": self.color,
            "dev_card_count": len(self.dev_cards),
            "knights_played": self.knights_played,
            "total_resources": self.total_resources,
            "settlements_left": self.settlements_left,
            "cities_left": self.cities_left,
            "roads_left": self.roads_left,
            "connected": self.connected,
        }


class GamePhase(Enum):
    LOBBY = "lobby"
    SETUP = "setup"
    SETUP_ROAD = "setup_road"
    ROLL = "roll"
    PIRATE_MOVE = "pirate_move"
    PIRATE_STEAL = "pirate_steal"
    DISCARD = "discard"
    MAIN = "main"
    FINISHED = "finished"


HEX_SIZE = 50


class HexMap:
    def __init__(self, radius: int = 2):
        self.radius = radius
        self.hexes: dict[int, HexTile] = {}
        self.vertices: dict[int, Vertex] = {}
        self.edges: dict[int, Edge] = {}
        self._hex_by_coord: dict[tuple, int] = {}
        self._next_hex_id = 0
        self._next_vertex_id = 0
        self._next_edge_id = 0
        self._generate()

    def _generate(self):
        terrain_pool = self._create_terrain_pool()
        number_pool = self._create_number_pool()
        random.shuffle(terrain_pool)

        coords = []
        for q in range(-self.radius, self.radius + 1):
            for r in range(-self.radius, self.radius + 1):
                if abs(q + r) <= self.radius:
                    coords.append((q, r))

        random.shuffle(coords)

        for q, r in coords:
            hex_id = self._next_hex_id
            self._next_hex_id += 1

            terrain = terrain_pool.pop() if terrain_pool else TerrainType.DESERT

            if terrain in (TerrainType.DESERT, TerrainType.RUINS):
                number_token = 0
            elif number_pool:
                number_token = number_pool.pop()
            else:
                number_token = random.choice([2, 3, 4, 5, 6, 8, 9, 10, 11, 12])

            discovery = None
            if terrain == TerrainType.RUINS:
                discovery = random.choice(list(DiscoveryType))

            tile = HexTile(
                hex_id=hex_id,
                q=q,
                r=r,
                terrain=terrain,
                number_token=number_token,
                discovery=discovery,
            )
            self.hexes[hex_id] = tile
            self._hex_by_coord[(q, r)] = hex_id

        self._generate_vertices_and_edges()
        self._place_ports()

    def _create_terrain_pool(self):
        if self.radius == 2:
            # Классика: 19 гексов. Руин нет (только если мод отключен)
            return (
                [TerrainType.FOREST] * 4
                + [TerrainType.HILLS] * 3
                + [TerrainType.FIELDS] * 4
                + [TerrainType.PASTURE] * 4
                + [TerrainType.MOUNTAINS] * 3
                + [TerrainType.DESERT] * 1
            )
        else:
            # Туман войны: 37 гексов. Много всего, плюс Руины по краям
            return (
                [TerrainType.FOREST] * 7
                + [TerrainType.HILLS] * 6
                + [TerrainType.FIELDS] * 7
                + [TerrainType.PASTURE] * 7
                + [TerrainType.MOUNTAINS] * 6
                + [TerrainType.DESERT] * 1
                + [TerrainType.RUINS] * 3
            )

    def _create_number_pool(self):
        base = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]
        if self.radius == 3:
            base = base + base  # Двойной набор цифр для большой карты
        random.shuffle(base)
        return base

    def _hex_to_pixel(self, q, r):
        x = HEX_SIZE * (math.sqrt(3) * q + math.sqrt(3) / 2 * r)
        y = HEX_SIZE * (3 / 2 * r)
        return x, y

    def _generate_vertices_and_edges(self):
        vertex_coord_to_id = {}
        edge_coord_to_id = {}

        for hex_id, tile in self.hexes.items():
            cx, cy = self._hex_to_pixel(tile.q, tile.r)
            hex_vertices = []

            for i in range(6):
                angle = math.pi / 3 * i - math.pi / 6
                vx = cx + HEX_SIZE * math.cos(angle)
                vy = cy + HEX_SIZE * math.sin(angle)
                key = (round(vx, 1), round(vy, 1))

                if key not in vertex_coord_to_id:
                    vid = self._next_vertex_id
                    self._next_vertex_id += 1
                    vertex_coord_to_id[key] = vid
                    self.vertices[vid] = Vertex(vertex_id=vid, x=vx, y=vy)

                vid = vertex_coord_to_id[key]
                hex_vertices.append(vid)
                if hex_id not in self.vertices[vid].adjacent_hexes:
                    self.vertices[vid].adjacent_hexes.append(hex_id)

            for i in range(6):
                v1 = hex_vertices[i]
                v2 = hex_vertices[(i + 1) % 6]
                edge_key = (min(v1, v2), max(v1, v2))

                if edge_key not in edge_coord_to_id:
                    eid = self._next_edge_id
                    self._next_edge_id += 1
                    edge_coord_to_id[edge_key] = eid
                    self.edges[eid] = Edge(edge_id=eid, vertices=edge_key)

                eid = edge_coord_to_id[edge_key]
                if hex_id not in self.edges[eid].adjacent_hexes:
                    self.edges[eid].adjacent_hexes.append(hex_id)

                for v in (v1, v2):
                    other = v2 if v == v1 else v1
                    if other not in self.vertices[v].adjacent_vertices:
                        self.vertices[v].adjacent_vertices.append(other)
                    if eid not in self.vertices[v].adjacent_edges:
                        self.vertices[v].adjacent_edges.append(eid)

    def _place_ports(self):
        port_types = [
            None,
            None,
            None,
            None,
            Resource.WOOD,
            Resource.BRICK,
            Resource.WHEAT,
            Resource.SHEEP,
            Resource.ORE,
        ]
        if self.radius == 3:
            port_types += [None, Resource.WOOD, Resource.WHEAT, Resource.SHEEP]

        random.shuffle(port_types)

        border_vertices = [
            vid for vid, v in self.vertices.items() if len(v.adjacent_hexes) < 3
        ]
        random.shuffle(border_vertices)

        placed = 0
        for vid in border_vertices:
            if placed >= len(port_types):
                break
            self.vertices[vid].is_port = True
            self.vertices[vid].port_type = port_types[placed]
            placed += 1

    def reveal_around(self, vertex_id, player_revealed_hexes):
        vertex = self.vertices[vertex_id]
        newly_revealed = []
        for hex_id in vertex.adjacent_hexes:
            if hex_id not in player_revealed_hexes:
                player_revealed_hexes.add(hex_id)
                newly_revealed.append(hex_id)
        return newly_revealed

    def get_initial_revealed(self, fog_of_war: bool):
        revealed = set()
        for hid, tile in self.hexes.items():
            if not fog_of_war:
                revealed.add(hid)
            else:
                # Открываем только центр (радиус <= 2)
                dist = max(abs(tile.q), abs(tile.r), abs(tile.q + tile.r))
                if dist <= 2:
                    revealed.add(hid)
        return revealed


@dataclass
class TradeOffer:
    from_player: int
    give: dict
    want: dict
    rejected_by: set = field(default_factory=set)


class Game:
    def __init__(
        self,
        room_id: str,
        max_players: int = 4,
        points_to_win: int = 10,
        fog_of_war: bool = False,
        fast_resources: bool = False,
        fast_start: bool = True,
        friendly_robber: bool = True,
        poor_tax: bool = False,
        roles: bool = False,
        events: bool = False,
        diplomacy: bool = False,
    ):
        self.room_id = room_id
        self.max_players = max_players
        self.points_to_win = points_to_win

        self.fog_of_war = fog_of_war
        self.fast_resources = fast_resources
        self.fast_start = fast_start
        self.friendly_robber = friendly_robber
        self.poor_tax = poor_tax
        self.roles_mod = roles
        self.events_mod = events
        self.diplomacy_mod = diplomacy

        # Если туман войны - карта 37 гексов. Иначе - 19.
        map_radius = 3 if self.fog_of_war else 2
        self.map = HexMap(radius=map_radius)

        self.phase = GamePhase.LOBBY
        self.turn = 0
        self.current_player_idx = 0
        self.dice_result = (0, 0)
        self.players: list[Player] = []
        self.colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12"]
        self.dev_card_deck = self._create_dev_deck()
        self.pirate_hex: Optional[int] = None
        self.longest_road_player: Optional[int] = None
        self.largest_army_player: Optional[int] = None
        self.log: list[dict] = []
        self.log_counter = 0
        self.pending_discards: dict[int, int] = {}
        self.last_setup_vertex: Optional[int] = None
        self.pending_pirate_victims: list[int] = []
        self.setup_order: list[int] = []
        self.setup_index: int = 0
        self.active_trade_offer: Optional[TradeOffer] = None
        self.bot_pids: set[int] = set()

        self._place_initial_pirate()

    def add_player(self, name: str) -> Optional[Player]:
        if len(self.players) >= self.max_players:
            return None
        if self.phase != GamePhase.LOBBY:
            return None

        pid = len(self.players)
        player = Player(
            player_id=pid,
            name=name,
            color=self.colors[pid],
            revealed_hexes=self.map.get_initial_revealed(self.fog_of_war),
        )
        self.players.append(player)
        return player

    def add_bot(self, name: str) -> Optional[Player]:
        player = self.add_player(name)
        if player:
            self.bot_pids.add(player.player_id)
            player.connected = True  # Боты всегда "онлайн"
        return player

    def _create_dev_deck(self):
        deck = (
            [DevCardType.KNIGHT] * 14
            + [DevCardType.VICTORY_POINT] * 5
            + [DevCardType.ROAD_BUILDING] * 2
            + [DevCardType.YEAR_OF_PLENTY] * 2
            + [DevCardType.MONOPOLY] * 2
            + [DevCardType.EXPLORER] * 3
            + [DevCardType.PIRATE_HUNTER] * 2
            + [DevCardType.ANCIENT_MAP] * 2
        )
        if self.diplomacy_mod:
            deck += [DevCardType.REBELLION] * 2
            deck += [DevCardType.TRADE_AGREEMENT] * 2
            deck += [DevCardType.SANCTIONS] * 2
        random.shuffle(deck)
        return deck

    def _place_initial_pirate(self):
        for hid, tile in self.map.hexes.items():
            if tile.terrain == TerrainType.DESERT:
                tile.has_pirate = True
                self.pirate_hex = hid
                return

        # Fallback, если на карте вдруг нет пустыни
        if self.map.hexes:
            hid = next(iter(self.map.hexes))
            self.map.hexes[hid].has_pirate = True
            self.pirate_hex = hid

    @property
    def current_player(self) -> Optional[Player]:
        if not self.players:
            return None
        return self.players[self.current_player_idx % len(self.players)]

    def _add_log(self, msg: str, player_id: Optional[int] = None):
        self.log_counter += 1
        entry = {"id": self.log_counter, "msg": msg, "player_id": player_id}
        self.log.append(entry)
        if len(self.log) > 100:
            self.log = self.log[-100:]

    def _ensure_active(self):
        if self.phase == GamePhase.FINISHED:
            return {"error": "Игра уже завершена"}
        return None

    def _parse_resource(self, value: str) -> Optional[Resource]:
        try:
            r = Resource(value)
            return None if r == Resource.NONE else r
        except Exception:
            return None

    def _bank_trade_rate(self, player_id: int, give_r: Resource) -> int:
        rate = 4

        for v in self.map.vertices.values():
            if v.building_owner != player_id or not v.is_port:
                continue
            if v.port_type is None:
                rate = min(rate, 3)
            elif v.port_type == give_r:
                rate = min(rate, 2)

        # ИСПРАВЛЕНО: Торговое соглашение применяется после портов
        if self.players[player_id].trade_agreement_turn == self.turn:
            rate = min(rate, 2)

        return rate

    def _player_reachable_vertices(self, player_id: int) -> set[int]:
        blocked = {
            vid
            for vid, v in self.map.vertices.items()
            if v.building_owner is not None and v.building_owner != player_id
        }
        reachable = set()
        q = deque()

        for vid, v in self.map.vertices.items():
            if v.building_owner == player_id:
                reachable.add(vid)
                q.append(vid)

        while q:
            vid = q.popleft()
            vertex = self.map.vertices[vid]
            for eid in vertex.adjacent_edges:
                edge = self.map.edges[eid]
                if edge.road_owner != player_id:
                    continue
                a, b = edge.vertices
                nxt = b if a == vid else a
                if nxt in blocked or nxt in reachable:
                    continue
                reachable.add(nxt)
                q.append(nxt)

        return reachable

    def _is_road_connected(self, player_id, edge_id):
        edge = self.map.edges.get(edge_id)
        if edge is None or not edge.is_empty:
            return False
        reachable = self._player_reachable_vertices(player_id)
        v1, v2 = edge.vertices
        return v1 in reachable or v2 in reachable

    def _has_any_buildable_road(self, player_id: int) -> bool:
        player = self.players[player_id]
        if player.roads_left <= 0:
            return False

        for eid, edge in self.map.edges.items():
            if edge.is_empty and self._is_road_connected(player_id, eid):
                return True
        return False

    def _is_vertex_connected(self, player_id, vertex_id):
        vertex = self.map.vertices[vertex_id]
        for eid in vertex.adjacent_edges:
            if self.map.edges[eid].road_owner == player_id:
                return True
        return False

    def _calculate_longest_road(self, player_id):
        player_edges = {
            eid for eid, e in self.map.edges.items() if e.road_owner == player_id
        }
        if not player_edges:
            return 0

        graph = defaultdict(set)
        for eid in player_edges:
            v1, v2 = self.map.edges[eid].vertices
            for va, vb in [(v1, v2), (v2, v1)]:
                vertex = self.map.vertices[va]
                if (
                    vertex.building_owner is not None
                    and vertex.building_owner != player_id
                ):
                    continue
                graph[va].add((vb, eid))

        max_length = 0

        def dfs(node, visited, length):
            nonlocal max_length
            max_length = max(max_length, length)
            for neighbor, eid in graph.get(node, set()):
                if eid not in visited:
                    visited.add(eid)
                    dfs(neighbor, visited, length + 1)
                    visited.remove(eid)

        start_vertices = set(
            v for eid in player_edges for v in self.map.edges[eid].vertices
        )
        for sv in start_vertices:
            dfs(sv, set(), 0)

        return max_length

    def _check_longest_road(self):
        # Исправлен баг: если текущий держатель потерял дорогу < 5 — сбрасываем
        current_holder = self.longest_road_player
        if current_holder is not None:
            holder_len = self._calculate_longest_road(current_holder)
            if holder_len >= 5:
                current_best = holder_len
                best_player = current_holder
            else:
                current_best = 4
                best_player = None
        else:
            current_best = 4
            best_player = None

        for p in self.players:
            length = self._calculate_longest_road(p.player_id)
            if length > current_best and length >= 5:
                current_best = length
                best_player = p.player_id

        if best_player != self.longest_road_player:
            self.longest_road_player = best_player
            if best_player is not None:
                self._add_log(
                    f"🛤️ {self.players[best_player].name}: Самая длинная дорога! ({current_best})"
                )
            else:
                self._add_log("🛤️ Никто не владеет самой длинной дорогой")

    def _check_largest_army(self):
        current_holder = self.largest_army_player
        current_best = (
            self.players[current_holder].knights_played
            if current_holder is not None
            else 2
        )

        best_player = current_holder
        best_knights = current_best

        for p in self.players:
            if p.knights_played > best_knights and p.knights_played >= 3:
                best_knights = p.knights_played
                best_player = p.player_id

        if best_player != self.largest_army_player:
            self.largest_army_player = best_player
            if best_player is not None:
                self._add_log(
                    f"⚔️ {self.players[best_player].name}: Самая большая армия! ({best_knights})"
                )

    def get_victory_points(self, player_id: int, public: bool = False) -> int:
        """
        public=True — считаем без скрытых VP (для показа другим игрокам).
        public=False — полный счёт (для самого игрока и проверки победы).
        """
        player = self.players[player_id]
        vp = 0

        for vid, vertex in self.map.vertices.items():
            if vertex.building_owner == player_id:
                if vertex.building_type == BuildingType.SETTLEMENT:
                    vp += 1
                elif vertex.building_type == BuildingType.CITY:
                    vp += 2

        if self.longest_road_player == player_id:
            vp += 2
        if self.largest_army_player == player_id:
            vp += 2

        if not public:
            vp += player.victory_points_hidden

        return vp

    def _check_victory(self, player_id):
        if self.phase == GamePhase.FINISHED:
            return
        vp = self.get_victory_points(player_id, public=False)
        if vp >= self.points_to_win:
            self.phase = GamePhase.FINISHED
            self._add_log(
                f"🏆 {self.players[player_id].name} ПОБЕДИЛ с {vp} очками! 🏆"
            )

    def _handle_discovery(self, player, tile):
        disc = tile.discovery
        if disc is None:
            return None

        msg = DISCOVERY_NAMES.get(disc, str(disc))
        tile.discovery = None

        if disc == DiscoveryType.TREASURE:
            for _ in range(2):
                r = random.choice(
                    [
                        Resource.WOOD,
                        Resource.BRICK,
                        Resource.WHEAT,
                        Resource.SHEEP,
                        Resource.ORE,
                    ]
                )
                player.add_resource(r)

        elif disc == DiscoveryType.ANCIENT_KNOWLEDGE:
            if self.dev_card_deck:
                card = self.dev_card_deck.pop()
                player.dev_cards.append(
                    DevCardInstance(
                        card_type=card,
                        bought_turn=self.turn,
                        playable_from_turn=self.turn + 1,
                    )
                )
                msg += f" → {DEV_CARD_NAMES.get(card, card.value)}"
            else:
                msg += " → Увы, колода карт развития пуста!"

        elif disc == DiscoveryType.CURSE:
            # --- ИСПРАВЛЕНО: Честный случайный выбор ресурсов на сброс ---
            pool = [r for r, amt in player.resources.items() for _ in range(amt)]
            to_lose = min(2, len(pool))
            for r in random.sample(pool, to_lose):
                player.resources[r] -= 1

        elif disc == DiscoveryType.FERTILE_LAND:
            tile.fertility_bonus = True

        elif disc == DiscoveryType.FORTIFICATION:
            player.has_fortification = True

        elif disc == DiscoveryType.LOST_TRIBE:
            player.victory_points_hidden += 1
            self._check_victory(player.player_id)

        self._add_log(f"🏛️ {player.name}: {msg}", player.player_id)
        return msg

    def _get_legal_targets(self, player_id: int) -> dict:
        out = {
            "setup_settlement_vertices": [],
            "setup_road_edges": [],
            "build_road_edges": [],
            "build_settlement_vertices": [],
            "build_city_vertices": [],
            "move_pirate_hexes": [],
        }

        if player_id < 0 or player_id >= len(self.players):
            return out

        player = self.players[player_id]

        if (
            self.phase == GamePhase.SETUP
            and self.setup_order
            and self.setup_order[self.setup_index] == player_id
        ):
            for vid, vertex in self.map.vertices.items():
                if not vertex.is_empty:
                    continue
                if any(
                    self.map.vertices[adj].building_type is not None
                    for adj in vertex.adjacent_vertices
                ):
                    continue
                out["setup_settlement_vertices"].append(vid)

        elif self.phase == GamePhase.SETUP_ROAD and self.last_setup_vertex is not None:
            for eid, edge in self.map.edges.items():
                if edge.is_empty and self.last_setup_vertex in edge.vertices:
                    out["setup_road_edges"].append(eid)

        elif self.phase == GamePhase.MAIN and player_id == self.current_player_idx:
            if (
                player.has_resources(COST_ROAD) or player.free_roads_pending > 0
            ) and player.roads_left > 0:
                out["build_road_edges"] = [
                    eid
                    for eid, edge in self.map.edges.items()
                    if edge.is_empty and self._is_road_connected(player_id, eid)
                ]
            if player.has_resources(COST_SETTLEMENT) and player.settlements_left > 0:
                for vid, vertex in self.map.vertices.items():
                    if not vertex.is_empty:
                        continue
                    if any(
                        not self.map.vertices[adj].is_empty
                        for adj in vertex.adjacent_vertices
                    ):
                        continue
                    if any(
                        self.map.edges[eid].road_owner == player_id
                        for eid in vertex.adjacent_edges
                    ):
                        out["build_settlement_vertices"].append(vid)

            if player.has_resources(COST_CITY) and player.cities_left > 0:
                out["build_city_vertices"] = [
                    vid
                    for vid, vertex in self.map.vertices.items()
                    if vertex.building_owner == player_id
                    and vertex.building_type == BuildingType.SETTLEMENT
                ]

        elif (
            self.phase == GamePhase.PIRATE_MOVE and player_id == self.current_player_idx
        ):
            out["move_pirate_hexes"] = [
                hid
                for hid, tile in self.map.hexes.items()
                if hid != self.pirate_hex and hid in player.revealed_hexes
            ]

        return out

    def _get_available_actions(self, player_id: int) -> list:
        actions = []
        is_my_turn = player_id == self.current_player_idx

        if self.phase == GamePhase.LOBBY:
            actions.append("wait")

        elif self.phase == GamePhase.SETUP:
            if self.setup_order and self.setup_order[self.setup_index] == player_id:
                actions.append("setup_settlement")

        elif self.phase == GamePhase.SETUP_ROAD:
            if self.setup_order and self.setup_order[self.setup_index] == player_id:
                actions.append("setup_road")

        elif self.phase == GamePhase.ROLL:
            if is_my_turn:
                actions.append("roll_dice")

        elif self.phase == GamePhase.DISCARD:
            if player_id in self.pending_discards:
                actions.append("discard")

        elif self.phase == GamePhase.PIRATE_MOVE:
            if is_my_turn:
                actions.append("move_pirate")

        elif self.phase == GamePhase.PIRATE_STEAL:
            if is_my_turn:
                actions.append("choose_pirate_victim")

        elif self.phase == GamePhase.MAIN:
            if is_my_turn:
                player = self.players[player_id]
                targets = self._get_legal_targets(player_id)

                actions.append("end_turn")

                if player.free_roads_pending > 0 and targets["build_road_edges"]:
                    actions.append("build_free_road")
                if (
                    player.has_resources(COST_ROAD)
                    and player.roads_left > 0
                    and targets["build_road_edges"]
                ):
                    actions.append("build_road")
                if (
                    player.has_resources(COST_SETTLEMENT)
                    and player.settlements_left > 0
                    and targets["build_settlement_vertices"]
                ):
                    actions.append("build_settlement")
                if (
                    player.has_resources(COST_CITY)
                    and player.cities_left > 0
                    and targets["build_city_vertices"]
                ):
                    actions.append("build_city")
                if player.has_resources(COST_DEV_CARD) and self.dev_card_deck:
                    actions.append("buy_dev_card")
                if (
                    any(
                        c.card_type != DevCardType.VICTORY_POINT
                        and self.turn >= c.playable_from_turn
                        for c in player.dev_cards
                    )
                    and not player.dev_card_played_this_turn
                ):
                    actions.append("play_dev_card")

                # --- ПРОВЕРКА НА САНКЦИИ (Блокировка торговли) ---
                # Если текущий ход меньше или равен ходу, до которого действуют санкции, торговать нельзя
                is_sanctioned = self.turn < player.sanctioned_until_turn

                if not is_sanctioned:
                    if any(
                        player.resources.get(r, 0)
                        >= self._bank_trade_rate(player_id, r)
                        for r in [
                            Resource.WOOD,
                            Resource.BRICK,
                            Resource.WHEAT,
                            Resource.SHEEP,
                            Resource.ORE,
                        ]
                    ):
                        actions.append("trade_bank")

                    # ИСПРАВЛЕНО: Предлагать обмен можно только если у тебя есть ресурсы и есть другие игроки
                    if player.total_resources > 0 and len(self.players) > 1:
                        actions.append("propose_trade")

        return actions

    def start_game(self):
        if self.phase != GamePhase.LOBBY:
            return {
                "ok": False,
                "already_started": True,
                "error": f"Игра уже началась или находится не в лобби (phase={self.phase.value})",
                "phase": self.phase.value,
                "players": len(self.players),
            }

        if len(self.players) < 2:
            return {
                "ok": False,
                "error": f"Нужно минимум 2 игрока (сейчас {len(self.players)})",
                "phase": self.phase.value,
                "players": len(self.players),
            }

        # Случайный порядок хода
        order = list(range(len(self.players)))
        random.shuffle(order)

        self.setup_order = order + list(reversed(order))
        self.setup_index = 0
        self.last_setup_vertex = None
        self.phase = GamePhase.SETUP
        self.current_player_idx = self.setup_order[self.setup_index]
        self.turn = 0

        self._add_log("🎮 Игра началась! Фаза расстановки.")

        if self.roles_mod:
            ROLES = [
                {"name": "⛏️ Шахтёр", "give": {Resource.ORE: 3}},
                {"name": "🪓 Лесоруб", "give": {Resource.WOOD: 2, Resource.BRICK: 1}},
                {"name": "🌾 Фермер", "give": {Resource.WHEAT: 2, Resource.SHEEP: 1}},
                {"name": "👑 Аристократ", "vp": 1},
                {"name": "⚓ Торговец", "give": {Resource.WHEAT: 1, Resource.ORE: 1}},
            ]
            available_roles = list(ROLES)
            random.shuffle(available_roles)

            for p in self.players:
                if not available_roles:
                    p.role_name = ""
                    continue

                role = available_roles.pop()
                p.role_name = role["name"]

                for r, amt in role.get("give", {}).items():
                    p.add_resource(r, amt)
                if role.get("vp"):
                    p.victory_points_hidden += role["vp"]

                self._add_log(f"🎭 {p.name} получает роль: {role['name']}")

        return {"ok": True}

    def setup_place_settlement(self, player_id: int, vertex_id: int):
        if self.phase != GamePhase.SETUP:
            return {"error": "Не фаза расстановки"}

        err = self._ensure_active()
        if err:
            return err

        expected = self.setup_order[self.setup_index]
        if player_id != expected:
            return {"error": "Сейчас не ваш ход"}

        player = self.players[player_id]
        vertex = self.map.vertices.get(vertex_id)
        if vertex is None or not vertex.is_empty:
            return {"error": "Нельзя строить здесь"}

        for adj_vid in vertex.adjacent_vertices:
            adj = self.map.vertices.get(adj_vid)
            if adj and not adj.is_empty:
                return {"error": "Слишком близко к другому зданию"}

        legal = self._get_legal_targets(player_id)["setup_settlement_vertices"]
        if vertex_id not in legal:
            return {"error": "Нельзя строить здесь"}

        is_second_round = self.setup_index >= len(self.players)

        # --- МОД СТОЛИЦЫ (Только для второго поселения!) ---
        if self.fast_start and is_second_round:
            if player.cities_left > 0:
                vertex.building_type = BuildingType.CITY
                player.cities_left -= 1
                self._add_log(f"🏙️ {player.name} основал Столицу!", player_id)
            else:
                vertex.building_type = BuildingType.SETTLEMENT
                player.settlements_left -= 1
                self._add_log(f"🏠 {player.name} построил поселение", player_id)
        else:
            vertex.building_type = BuildingType.SETTLEMENT
            player.settlements_left -= 1
            self._add_log(f"🏠 {player.name} построил поселение", player_id)

        vertex.building_owner = player_id
        self.last_setup_vertex = vertex_id

        newly = self.map.reveal_around(vertex_id, player.revealed_hexes)
        discovery_msgs = []
        for hid in newly:
            tile = self.map.hexes[hid]
            if tile.terrain == TerrainType.RUINS and tile.discovery:
                msg = self._handle_discovery(player, tile)
                if msg:
                    discovery_msgs.append(msg)

        if is_second_round:
            for hid in vertex.adjacent_hexes:
                tile = self.map.hexes[hid]
                if tile.resource != Resource.NONE:
                    start_amount = 2 if self.fast_resources else 1
                    player.add_resource(tile.resource, start_amount)

        self.phase = GamePhase.SETUP_ROAD
        return {
            "ok": True,
            "discovery": "; ".join(discovery_msgs) if discovery_msgs else None,
        }

    def setup_place_road(self, player_id: int, edge_id: int):
        if self.phase != GamePhase.SETUP_ROAD:
            return {"error": "Не фаза установки дороги"}

        err = self._ensure_active()
        if err:
            return err

        expected = self.setup_order[self.setup_index]
        if player_id != expected:
            return {"error": "Сейчас не ваш ход"}

        player = self.players[player_id]
        if player.roads_left <= 0:
            return {"error": "Закончились дороги"}

        edge = self.map.edges.get(edge_id)
        if edge is None or not edge.is_empty:
            return {"error": "Нельзя строить здесь"}

        v1, v2 = edge.vertices
        if self.last_setup_vertex not in (v1, v2):
            return {"error": "Дорога должна быть от поселения"}

        legal = self._get_legal_targets(player_id)["setup_road_edges"]
        if edge_id not in legal:
            return {"error": "Нельзя строить здесь"}

        edge.road_owner = player_id
        player.roads_left -= 1
        self._add_log(f"🛤️ {player.name} построил дорогу", player_id)

        self.setup_index += 1
        if self.setup_index >= len(self.setup_order):
            self.phase = GamePhase.ROLL
            self.current_player_idx = self.setup_order[0]
            self.turn = 1
            self._add_log("✅ Расстановка завершена! Начинается игра.")
        else:
            self.current_player_idx = self.setup_order[self.setup_index]
            self.phase = GamePhase.SETUP

        return {"ok": True}

    def roll_dice(self, player_id: int):
        if self.phase != GamePhase.ROLL:
            return {"error": "Сейчас не фаза броска"}

        err = self._ensure_active()
        if err:
            return err

        if player_id != self.current_player_idx:
            return {"error": "Не ваш ход"}

        # Очищаем старые предложения обмена игроков в начале нового хода
        self.active_trade_offer = None

        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        self.dice_result = (d1, d2)
        total = d1 + d2

        self._add_log(f"🎲 {self.current_player.name}: {d1}+{d2}={total}", player_id)

        # --- МОД: СЛУЧАЙНЫЕ СОБЫТИЯ (Срабатывает при дублях, кроме 7) ---
        if getattr(self, "events_mod", False) and d1 == d2 and total != 7:
            event_type = random.choice(["gold", "flood", "bounty"])

            if event_type == "gold":
                for p in self.players:
                    r = random.choice(
                        [
                            Resource.WOOD,
                            Resource.BRICK,
                            Resource.WHEAT,
                            Resource.SHEEP,
                            Resource.ORE,
                        ]
                    )
                    p.add_resource(r)
                self._add_log(
                    "✨ СОБЫТИЕ: Золотая лихорадка! Все получили по 1 случайному ресурсу."
                )

            elif event_type == "flood":
                for p in self.players:
                    pool = [r for r, a in p.resources.items() if a > 0]
                    if pool:
                        p.resources[random.choice(pool)] -= 1
                self._add_log(
                    "🌊 СОБЫТИЕ: Наводнение! Все игроки потеряли по 1 случайному ресурсу."
                )

            elif event_type == "bounty":
                if self.dev_card_deck:
                    # Находим игроков с минимальным количеством очков
                    min_vp = min(
                        self.get_victory_points(p.player_id, public=True)
                        for p in self.players
                    )
                    poor_players = [
                        p
                        for p in self.players
                        if self.get_victory_points(p.player_id, public=True) == min_vp
                    ]
                    lucky = random.choice(poor_players)

                    # Дарим карту
                    card = self.dev_card_deck.pop()
                    lucky.dev_cards.append(
                        DevCardInstance(
                            card_type=card,
                            bought_turn=self.turn,
                            playable_from_turn=self.turn + 1,
                        )
                    )
                    self._add_log(
                        f"🎁 СОБЫТИЕ: Гуманитарная помощь! Отстающий ({lucky.name}) получает карту развития."
                    )

        # --- ОБЫЧНАЯ ЛОГИКА КУБИКОВ ---
        if total == 7:
            has_discard = False
            for p in self.players:
                if p.total_resources > 7:
                    self.pending_discards[p.player_id] = p.total_resources // 2
                    has_discard = True

            if has_discard:
                self.phase = GamePhase.DISCARD
                self._add_log("💀 Выпало 7! Игроки сбрасывают лишние ресурсы.")
            else:
                self.phase = GamePhase.PIRATE_MOVE
                if not self._get_legal_targets(self.current_player_idx)[
                    "move_pirate_hexes"
                ]:
                    self.phase = GamePhase.MAIN
                    self._add_log(
                        "🏴‍☠️ Пирату некуда идти из-за тумана. Переход к основной фазе."
                    )
                else:
                    self._add_log("🏴‍☠️ Переместите пирата!")
        else:
            self._distribute_resources(total)
            self.phase = GamePhase.MAIN

        return {"ok": True, "dice": [d1, d2], "total": total}

    def discard_resources(self, player_id: int, discards: dict):
        if self.phase != GamePhase.DISCARD:
            return {"error": "Не фаза сброса"}

        err = self._ensure_active()
        if err:
            return err

        if player_id not in self.pending_discards:
            return {"error": "Вам не нужно сбрасывать"}

        try:
            needed = self.pending_discards[player_id]
            normalized = {}
            total_discarding = 0
            for r_str, amt in discards.items():
                r = Resource(r_str)
                if r == Resource.NONE:
                    return {"error": "Неверный ресурс"}
                amt = int(amt)
                if amt < 0:
                    return {"error": "Неверное количество"}
                normalized[r] = amt
                total_discarding += amt
        except Exception:
            return {"error": "Некорректные данные"}

        if total_discarding != needed:
            return {"error": f"Нужно сбросить ровно {needed}"}

        player = self.players[player_id]
        for r, amt in normalized.items():
            if player.resources.get(r, 0) < amt:
                return {"error": f"Недостаточно {r.value}"}

        for r, amt in normalized.items():
            player.resources[r] -= amt

        del self.pending_discards[player_id]
        self._add_log(f"♻️ {player.name} сбросил ресурсы", player_id)

        if not self.pending_discards:
            self.phase = GamePhase.PIRATE_MOVE

        return {"ok": True}

    def move_pirate(self, player_id: int, hex_id: int):
        if self.phase != GamePhase.PIRATE_MOVE:
            return {"error": "Не фаза перемещения пирата"}

        err = self._ensure_active()
        if err:
            return err

        if player_id != self.current_player_idx:
            return {"error": "Не ваш ход"}

        tile = self.map.hexes.get(hex_id)
        if tile is None:
            return {"error": "Неверный тайл"}
        if hex_id == self.pirate_hex:
            return {"error": "Пират уже здесь"}

        player = self.players[player_id]
        if hex_id not in player.revealed_hexes:
            return {"error": "Нельзя ставить пирата на неизвестный тайл"}

        if self.pirate_hex is not None:
            self.map.hexes[self.pirate_hex].has_pirate = False

        tile.has_pirate = True
        self.pirate_hex = hex_id

        victims = set()
        for vid, vertex in self.map.vertices.items():
            if hex_id not in vertex.adjacent_hexes:
                continue
            if vertex.building_owner is None or vertex.building_owner == player_id:
                continue

            victim = self.players[vertex.building_owner]
            if victim.has_fortification:
                continue

            if self.friendly_robber:
                # ИСПРАВЛЕНО: проверяем публичные очки, а не скрытые!
                victim_vp = self.get_victory_points(victim.player_id, public=True)
                if victim_vp <= 2:
                    continue

            if victim.total_resources > 0:
                victims.add(vertex.building_owner)

        # ИСПРАВЛЕНО: Жёстко ветвим логику. Если есть жертвы - воруем, если нет - идём в MAIN.
        if victims:
            self.pending_pirate_victims = sorted(list(victims))
            self.phase = GamePhase.PIRATE_STEAL
            self._add_log(
                f"🏴‍☠️ {player.name} переместил пирата. Выберите жертву.", player_id
            )
            return {
                "ok": True,
                "needs_steal": True,
                "victims": self.pending_pirate_victims,
            }
        else:
            self.pending_pirate_victims = []
            self.phase = GamePhase.MAIN
            # ИСПРАВЛЕНО: Пишем поясняющий лог
            self._add_log(
                f"🏴‍☠️ {player.name} переместил пирата (грабить некого)", player_id
            )
            return {"ok": True, "stolen": None}

    def choose_pirate_victim(self, player_id: int, victim_id: int):
        if self.phase != GamePhase.PIRATE_STEAL:
            return {"error": "Не фаза выбора жертвы"}

        err = self._ensure_active()
        if err:
            return err

        if player_id != self.current_player_idx:
            return {"error": "Не ваш ход"}
        if victim_id not in self.pending_pirate_victims:
            return {"error": "Неверная жертва"}

        victim = self.players[victim_id]
        # Исправлен баг: честная случайная кража (по количеству карточек, а не типов)
        pool = [r for r, amt in victim.resources.items() for _ in range(amt)]
        if not pool:
            return {"error": "У жертвы нет ресурсов"}

        r = random.choice(pool)
        victim.resources[r] -= 1
        self.players[player_id].add_resource(r)

        self._add_log(
            f"🏴‍☠️ {self.players[player_id].name} украл {r.value} у {victim.name}",
            player_id,
        )

        self.pending_pirate_victims = []
        self.phase = GamePhase.MAIN
        return {"ok": True, "stolen": {"from": victim.name, "resource": r.value}}

    def _distribute_resources(self, number: int):
        got_resources_this_turn = {p.player_id: False for p in self.players}

        for hid, tile in self.map.hexes.items():
            if tile.number_token != number or tile.has_pirate:
                continue
            if tile.terrain in (TerrainType.DESERT, TerrainType.RUINS):
                continue

            resource = tile.resource
            for vid, vertex in self.map.vertices.items():
                if hid not in vertex.adjacent_hexes:
                    continue
                if vertex.building_owner is None:
                    continue

                player = self.players[vertex.building_owner]
                base = 2 if vertex.building_type == BuildingType.CITY else 1
                if self.fast_resources:
                    base *= 2
                if tile.fertility_bonus:
                    base += 1
                amount = base

                player.add_resource(resource, amount)
                got_resources_this_turn[player.player_id] = True
                self._add_log(
                    f"📦 {player.name} +{amount} {resource.value}",
                    vertex.building_owner,
                )

        # Мод "Пособие по безработице"
        if self.poor_tax:
            for pid, got_something in got_resources_this_turn.items():
                if not got_something:
                    # Даем случайный ресурс бедолаге
                    r = random.choice(
                        [
                            Resource.WOOD,
                            Resource.BRICK,
                            Resource.WHEAT,
                            Resource.SHEEP,
                            Resource.ORE,
                        ]
                    )
                    self.players[pid].add_resource(r, 1)
                    self._add_log(
                        f"🪙 {self.players[pid].name} получил пособие (+1 {r.value})",
                        pid,
                    )

    def build_road(self, player_id: int, edge_id: int):
        if self.phase != GamePhase.MAIN:
            return {"error": "Не основная фаза"}

        err = self._ensure_active()
        if err:
            return err

        if player_id != self.current_player_idx:
            return {"error": "Не ваш ход"}

        player = self.players[player_id]
        edge = self.map.edges.get(edge_id)

        if edge is None or not edge.is_empty:
            return {"error": "Нельзя строить здесь"}
        if player.roads_left <= 0:
            return {"error": "Закончились дороги"}
        if not self._is_road_connected(player_id, edge_id):
            return {"error": "Дорога не связана"}
        if not player.pay_resources(COST_ROAD):
            return {"error": "Не хватает ресурсов"}

        edge.road_owner = player_id
        player.roads_left -= 1
        self._add_log(f"🛤️ {player.name} построил дорогу", player_id)
        self._check_longest_road()
        self._check_victory(player_id)
        return {"ok": True}

    def build_free_road(self, player_id: int, edge_id: int):
        if self.phase != GamePhase.MAIN:
            return {"error": "Не основная фаза"}

        err = self._ensure_active()
        if err:
            return err

        if player_id != self.current_player_idx:
            return {"error": "Не ваш ход"}

        player = self.players[player_id]
        edge = self.map.edges.get(edge_id)

        if edge is None or not edge.is_empty:
            return {"error": "Нельзя строить здесь"}
        if player.free_roads_pending <= 0:
            return {"error": "Нет бесплатных дорог"}
        if player.roads_left <= 0:
            return {"error": "Закончились дороги"}
        if not self._is_road_connected(player_id, edge_id):
            return {"error": "Дорога не связана"}

        edge.road_owner = player_id
        player.roads_left -= 1
        player.free_roads_pending -= 1
        self._add_log(f"🛤️ {player.name} построил бесплатную дорогу", player_id)
        self._check_longest_road()
        self._check_victory(player_id)
        return {"ok": True}

    def build_settlement(self, player_id: int, vertex_id: int):
        if self.phase != GamePhase.MAIN:
            return {"error": "Не основная фаза"}

        err = self._ensure_active()
        if err:
            return err

        if player_id != self.current_player_idx:
            return {"error": "Не ваш ход"}

        player = self.players[player_id]
        vertex = self.map.vertices.get(vertex_id)

        if vertex is None or not vertex.is_empty:
            return {"error": "Нельзя строить здесь"}
        if player.settlements_left <= 0:
            return {"error": "Закончились поселения"}
        for adj_vid in vertex.adjacent_vertices:
            if not self.map.vertices[adj_vid].is_empty:
                return {"error": "Слишком близко"}
        if not self._is_vertex_connected(player_id, vertex_id):
            return {"error": "Не связано с дорогой"}

        legal = self._get_legal_targets(player_id)["build_settlement_vertices"]
        if vertex_id not in legal:
            return {"error": "Нельзя строить здесь"}

        if not player.pay_resources(COST_SETTLEMENT):
            return {"error": "Не хватает ресурсов"}

        vertex.building_type = BuildingType.SETTLEMENT
        vertex.building_owner = player_id
        player.settlements_left -= 1

        newly = self.map.reveal_around(vertex_id, player.revealed_hexes)
        discovery_msgs = []
        for hid in newly:
            tile = self.map.hexes[hid]
            if tile.terrain == TerrainType.RUINS and tile.discovery:
                msg = self._handle_discovery(player, tile)
                if msg:
                    discovery_msgs.append(msg)

        self._add_log(f"🏠 {player.name} построил поселение", player_id)
        self._check_longest_road()
        self._check_victory(player_id)
        return {
            "ok": True,
            "discovery": "; ".join(discovery_msgs) if discovery_msgs else None,
        }

    def build_city(self, player_id: int, vertex_id: int):
        if self.phase != GamePhase.MAIN:
            return {"error": "Не основная фаза"}

        err = self._ensure_active()
        if err:
            return err

        if player_id != self.current_player_idx:
            return {"error": "Не ваш ход"}

        player = self.players[player_id]
        vertex = self.map.vertices.get(vertex_id)

        if vertex is None:
            return {"error": "Нет такой вершины"}
        if vertex.building_owner != player_id:
            return {"error": "Не ваше здание"}
        if vertex.building_type != BuildingType.SETTLEMENT:
            return {"error": "Можно улучшить только поселение"}
        if player.cities_left <= 0:
            return {"error": "Закончились города"}

        legal = self._get_legal_targets(player_id)["build_city_vertices"]
        if vertex_id not in legal:
            return {"error": "Нельзя улучшить здесь"}

        if not player.pay_resources(COST_CITY):
            return {"error": "Не хватает ресурсов"}

        vertex.building_type = BuildingType.CITY
        player.settlements_left += 1
        player.cities_left -= 1
        self._add_log(f"🏙️ {player.name} построил город", player_id)
        self._check_victory(player_id)
        return {"ok": True}

    def buy_dev_card(self, player_id: int):
        if self.phase != GamePhase.MAIN:
            return {"error": "Не основная фаза"}

        err = self._ensure_active()
        if err:
            return err

        if player_id != self.current_player_idx:
            return {"error": "Не ваш ход"}

        player = self.players[player_id]
        if not self.dev_card_deck:
            return {"error": "Колода пуста"}
        if not player.pay_resources(COST_DEV_CARD):
            return {"error": "Не хватает ресурсов"}

        card = self.dev_card_deck.pop()
        player.dev_cards.append(
            DevCardInstance(
                card_type=card,
                bought_turn=self.turn,
                playable_from_turn=self.turn + 1,
            )
        )

        if card == DevCardType.VICTORY_POINT:
            player.victory_points_hidden += 1
            self._check_victory(player_id)

        self._add_log(f"🃏 {player.name} купил карту развития", player_id)
        return {"ok": True, "card": card.value}

    def play_dev_card(self, player_id: int, card_type: str, params: dict = None):
        if self.phase != GamePhase.MAIN:
            return {"error": "Не основная фаза"}

        err = self._ensure_active()
        if err:
            return err

        if player_id != self.current_player_idx:
            return {"error": "Не ваш ход"}

        player = self.players[player_id]

        if player.dev_card_played_this_turn:
            return {"error": "За ход можно сыграть только одну карту развития"}

        try:
            card = DevCardType(card_type)
        except ValueError:
            return {"error": "Неизвестная карта"}

        if card == DevCardType.VICTORY_POINT:
            return {"error": "Эта карта играется автоматически"}

        playable = None
        for inst in player.dev_cards:
            if inst.card_type == card and self.turn >= inst.playable_from_turn:
                playable = inst
                break

        if playable is None:
            return {"error": "У вас нет такой карты или она ещё недоступна"}

        params = params or {}

        def consume_card():
            player.dev_cards.remove(playable)
            player.dev_card_played_this_turn = True

        if card == DevCardType.KNIGHT:
            consume_card()
            player.knights_played += 1
            self._check_largest_army()
            self._check_victory(player_id)

            legal = self._get_legal_targets(player_id)["move_pirate_hexes"]
            if legal:
                self.phase = GamePhase.PIRATE_MOVE
                self._add_log(f"⚔️ {player.name} сыграл Рыцаря!", player_id)
                return {"ok": True, "action": "move_pirate"}
            else:
                self.phase = GamePhase.MAIN
                self._add_log(
                    f"⚔️ {player.name} сыграл Рыцаря, но пирату некуда идти",
                    player_id,
                )
                return {"ok": True}

        if card == DevCardType.ROAD_BUILDING:
            consume_card()
            player.free_roads_pending = 2
            self._add_log(f"🛤️ {player.name} сыграл Строительство дорог", player_id)
            return {"ok": True, "action": "build_2_roads", "free_roads": 2}

        if card == DevCardType.YEAR_OF_PLENTY:
            r1 = self._parse_resource(params.get("resource1", ""))
            r2 = self._parse_resource(params.get("resource2", ""))
            if not r1 or not r2:
                return {"error": "Укажите 2 корректных ресурса"}
            consume_card()
            player.add_resource(r1)
            player.add_resource(r2)
            self._add_log(f"🌽 {player.name}: Год изобилия", player_id)
            return {"ok": True}

        if card == DevCardType.MONOPOLY:
            target = self._parse_resource(params.get("resource", ""))
            if not target:
                return {"error": "Укажите корректный ресурс"}

            consume_card()

            total_stolen = 0
            details = []

            for other in self.players:
                if other.player_id == player_id:
                    continue
                amt = other.resources.get(target, 0)
                if amt > 0:
                    other.resources[target] = 0
                    player.add_resource(target, amt)
                    total_stolen += amt
                    details.append(f"{other.name}: -{amt}")

            details_str = ", ".join(details)
            self._add_log(
                f"💰 {player.name}: Монополия на {target.value} "
                f"(+{total_stolen}) [{details_str}]",
                player_id,
            )
            return {"ok": True, "stolen": total_stolen}

        if card == DevCardType.EXPLORER:
            hex_id = params.get("hex_id")
            if hex_id is None:
                return {"error": "Укажите тайл"}
            try:
                hex_id = int(hex_id)
            except Exception:
                return {"error": "Неверный тайл"}

            tile = self.map.hexes.get(hex_id)
            if tile is None:
                return {"error": "Неверный тайл"}
            if hex_id in player.revealed_hexes:
                return {"error": "Этот тайл уже открыт"}

            unrevealed = [
                hid for hid in self.map.hexes if hid not in player.revealed_hexes
            ]
            if not unrevealed:
                return {"error": "Вся карта уже открыта!"}

            consume_card()
            player.revealed_hexes.add(hex_id)

            discovery_msg = None
            if tile.terrain == TerrainType.RUINS and tile.discovery:
                discovery_msg = self._handle_discovery(player, tile)

            self._add_log(f"🧭 {player.name} исследовал территорию", player_id)
            return {"ok": True, "discovery": discovery_msg}

        if card == DevCardType.PIRATE_HUNTER:
            consume_card()
            if self.pirate_hex is not None:
                self.map.hexes[self.pirate_hex].has_pirate = False
            self.pirate_hex = None

            for hid, tile in self.map.hexes.items():
                if tile.terrain == TerrainType.DESERT:
                    tile.has_pirate = True
                    self.pirate_hex = hid
                    break
            else:
                if self.map.hexes:
                    hid = next(iter(self.map.hexes))
                    self.map.hexes[hid].has_pirate = True
                    self.pirate_hex = hid

            self._add_log(f"🏹 {player.name} прогнал пирата!", player_id)
            return {"ok": True}

        if card == DevCardType.ANCIENT_MAP:
            consume_card()
            unrevealed = [
                hid for hid in self.map.hexes if hid not in player.revealed_hexes
            ]
            random.shuffle(unrevealed)
            revealed_count = min(3, len(unrevealed))
            for hid in unrevealed[:revealed_count]:
                player.revealed_hexes.add(hid)
            self._add_log(
                f"🗺️ {player.name}: Древняя карта (открыто {revealed_count} тайлов)",
                player_id,
            )
            return {"ok": True, "revealed": revealed_count}

        if card == DevCardType.REBELLION:
            consume_card()
            for p in self.players:
                if p.player_id != player_id:
                    pool = [r for r, a in p.resources.items() if a > 0]
                    if pool:
                        p.resources[random.choice(pool)] -= 1
            self._add_log(
                f"🔥 {player.name} спонсирует Восстание! Все остальные игроки теряют по 1 ресурсу.",
                player_id,
            )
            return {"ok": True}

        if card == DevCardType.TRADE_AGREEMENT:
            consume_card()
            player.trade_agreement_turn = self.turn
            self._add_log(
                f"🤝 {player.name} заключает Торговое соглашение (обмен с банком 2:1 до конца хода).",
                player_id,
            )
            return {"ok": True}

        if card == DevCardType.KNIGHT:
            consume_card()

            player.knights_played += 1

            self._check_largest_army()
            self._check_victory(player_id)

            # СНАЧАЛА меняем фазу
            self.phase = GamePhase.PIRATE_MOVE

            legal = self._get_legal_targets(player_id)["move_pirate_hexes"]

            if legal:
                self._add_log(
                    f"⚔️ {player.name} сыграл Рыцаря!",
                    player_id,
                )

                return {
                    "ok": True,
                    "action": "move_pirate",
                }

            # если реально некуда двигать
            self.phase = GamePhase.MAIN

            self._add_log(
                f"⚔️ {player.name} сыграл Рыцаря, но пирату некуда идти",
                player_id,
            )

            return {"ok": True}

        return {"error": "Неизвестное действие"}

    def trade_with_bank(self, player_id: int, give: str, receive: str):
        if self.phase != GamePhase.MAIN:
            return {"error": "Не основная фаза"}

        err = self._ensure_active()
        if err:
            return err

        if player_id != self.current_player_idx:
            return {"error": "Не ваш ход"}

        player = self.players[player_id]

        if self.turn < player.sanctioned_until_turn:
            return {"error": "Вы под санкциями и не можете торговать"}

        if give == receive:
            return {"error": "Нельзя менять ресурс на сам себя"}

        give_r = self._parse_resource(give)
        recv_r = self._parse_resource(receive)

        if not give_r or not recv_r:
            return {"error": "Неверный ресурс"}

        rate = self._bank_trade_rate(player_id, give_r)

        if player.resources.get(give_r, 0) < rate:
            return {"error": f"Нужно минимум {rate} {give}"}

        player.resources[give_r] -= rate
        player.add_resource(recv_r)
        self._add_log(f"🔄 {player.name}: {rate}×{give} → {receive}", player_id)
        return {"ok": True, "rate": rate}

    def propose_trade(self, player_id: int, give: dict, want: dict):
        if self.phase != GamePhase.MAIN or player_id != self.current_player_idx:
            return {"error": "Нельзя предложить обмен сейчас"}

        player = self.players[player_id]

        # ИСПРАВЛЕНО: Проверка санкций на сервере
        if self.turn < player.sanctioned_until_turn:
            return {"error": "Вы под санкциями и не можете торговать"}

        give_res, want_res = {}, {}
        for r_str, amt in give.items():
            r = self._parse_resource(r_str)
            if r and int(amt) > 0:
                give_res[r] = int(amt)
        for r_str, amt in want.items():
            r = self._parse_resource(r_str)
            if r and int(amt) > 0:
                want_res[r] = int(amt)

        if not give_res or not want_res:
            return {"error": "Пустой обмен"}
        if not self.players[player_id].has_resources(give_res):
            return {"error": "Не хватает ресурсов для предложения"}

        self.active_trade_offer = TradeOffer(player_id, give_res, want_res)
        self._add_log(f"📣 {self.players[player_id].name} предложил обмен!", player_id)
        return {"ok": True}

    def respond_trade(self, player_id: int, accept: bool):
        if self.phase != GamePhase.MAIN:
            return {"error": "Нельзя торговать вне основной фазы"}

        offer = self.active_trade_offer
        if not offer or offer.from_player == player_id:
            return {"error": "Нет активного обмена"}

        if accept:
            p_from = self.players[offer.from_player]
            p_to = self.players[player_id]

            if self.turn < p_to.sanctioned_until_turn:
                return {"error": "Вы под санкциями и не можете принимать обмен"}

            if not p_to.has_resources(offer.want):
                return {"error": "У вас нет нужных ресурсов"}
            if not p_from.has_resources(offer.give):
                self.active_trade_offer = None
                return {"error": "У предлагающего больше нет этих ресурсов"}

            # Проводим обмен
            p_from.pay_resources(offer.give)
            p_to.pay_resources(offer.want)
            for r, amt in offer.want.items():
                p_from.add_resource(r, amt)
            for r, amt in offer.give.items():
                p_to.add_resource(r, amt)

            self._add_log(f"🤝 {p_from.name} и {p_to.name} совершили обмен!")
            self.active_trade_offer = None
        else:
            offer.rejected_by.add(player_id)
            connected_others = {
                p.player_id
                for p in self.players
                if p.connected and p.player_id != offer.from_player
            }
            if offer.rejected_by >= connected_others:
                self.active_trade_offer = None
                self._add_log("🚫 Предложение обмена отклонено всеми")

        return {"ok": True}

    def cancel_trade(self, player_id: int):
        if self.active_trade_offer and self.active_trade_offer.from_player == player_id:
            self.active_trade_offer = None
            return {"ok": True}
        return {"error": "Невозможно отменить"}

    def end_turn(self, player_id: int):
        if player_id != self.current_player_idx:
            return {"error": "Не ваш ход"}
        if self.phase != GamePhase.MAIN:
            return {"error": "Нельзя завершить ход сейчас"}

        err = self._ensure_active()
        if err:
            return err

        player = self.players[player_id]

        # --- ИСПРАВЛЕНО: Предотвращение софтлока ---
        if player.free_roads_pending > 0:
            if player.roads_left > 0 and self._has_any_buildable_road(player_id):
                return {"error": "Сначала используйте бесплатные дороги"}
            else:
                self._add_log(
                    f"⚠️ У {player.name} сгорели оставшиеся бесплатные дороги.",
                    player_id,
                )

        self.active_trade_offer = None
        player.dev_card_played_this_turn = False
        player.free_roads_pending = 0

        self.current_player_idx = (self.current_player_idx + 1) % len(self.players)
        self.turn += 1
        self.phase = GamePhase.ROLL

        self._add_log(f"⏭️ Ход переходит к {self.current_player.name}")
        return {"ok": True}

    def get_state_for_player(self, player_id: int) -> dict:
        player = self.players[player_id]

        hexes = [
            self.map.hexes[hid].to_dict(revealed=(hid in player.revealed_hexes))
            for hid in sorted(self.map.hexes)
        ]

        # В fog of war свои постройки/дороги всегда видны владельцу
        def vertex_visible(v: Vertex):
            if not self.fog_of_war:
                return True
            if v.building_owner == player_id:
                return True
            return any(h in player.revealed_hexes for h in v.adjacent_hexes)

        def edge_visible(e: Edge):
            if not self.fog_of_war:
                return True
            if e.road_owner == player_id:
                return True
            return any(h in player.revealed_hexes for h in e.adjacent_hexes)

        vertices = [
            self.map.vertices[vid].to_dict()
            for vid in sorted(self.map.vertices)
            if vertex_visible(self.map.vertices[vid])
        ]

        edges = [
            self.map.edges[eid].to_dict()
            for eid in sorted(self.map.edges)
            if edge_visible(self.map.edges[eid])
        ]

        # Кешируем длины дорог
        road_lengths = {
            p.player_id: self._calculate_longest_road(p.player_id) for p in self.players
        }

        players_public = []
        for p in self.players:
            d = p.to_dict_public()
            d["victory_points"] = self.get_victory_points(
                p.player_id, public=(p.player_id != player_id)
            )
            d["longest_road"] = road_lengths[p.player_id]
            d["has_longest_road"] = self.longest_road_player == p.player_id
            d["has_largest_army"] = self.largest_army_player == p.player_id
            players_public.append(d)

        my_data = player.to_dict_private(self.turn)
        my_data["victory_points"] = self.get_victory_points(player_id, public=False)
        my_data["reconnect_token"] = player.reconnect_token

        available_actions = self._get_available_actions(player_id)
        legal_targets = self._get_legal_targets(player_id)

        trade_offer_data = None
        if self.active_trade_offer:
            o = self.active_trade_offer
            trade_offer_data = {
                "from_id": o.from_player,
                "from_name": self.players[o.from_player].name,
                "give": {r.value: amt for r, amt in o.give.items()},
                "want": {r.value: amt for r, amt in o.want.items()},
                "rejected_by_me": player_id in o.rejected_by,
                "can_accept": (
                    player_id != o.from_player
                    and self.turn >= self.players[player_id].sanctioned_until_turn
                    and self.players[player_id].has_resources(o.want)
                ),
            }

        winner_id = None
        winner_name = None
        if self.phase == GamePhase.FINISHED:
            best_player = max(
                self.players,
                key=lambda p: self.get_victory_points(p.player_id, public=False),
            )
            winner_id = best_player.player_id
            winner_name = best_player.name

        return {
            "room_id": self.room_id,
            "phase": self.phase.value,
            "turn": self.turn,
            "current_player": self.current_player_idx,
            "dice": list(self.dice_result),
            "hexes": hexes,
            "vertices": vertices,
            "edges": edges,
            "players": players_public,
            "me": my_data,
            "my_id": player_id,
            "log": self.log[-20:],
            "available_actions": available_actions,
            "legal_targets": legal_targets,
            "pending_pirate_victims": (
                self.pending_pirate_victims
                if self.phase == GamePhase.PIRATE_STEAL
                and player_id == self.current_player_idx
                else []
            ),
            "points_to_win": self.points_to_win,
            "pending_discards": (
                self.pending_discards.get(player_id, 0)
                if self.phase == GamePhase.DISCARD
                else 0
            ),
            "trade_offer": trade_offer_data,
            "winner_id": winner_id,
            "winner_name": winner_name,
        }
