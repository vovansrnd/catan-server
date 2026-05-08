from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from game_engine import (
    COST_CITY,
    COST_DEV_CARD,
    COST_ROAD,
    COST_SETTLEMENT,
    BuildingType,
    DevCardType,
    Game,
    GamePhase,
    Resource,
    TerrainType,
)


@dataclass
class Personality:
    greed: float = 1.0
    risk: float = 1.0
    aggression: float = 1.0
    expansion: float = 1.0
    devcards: float = 1.0
    trading: float = 1.0
    randomness: float = 0.15


BOT_PERSONALITIES = {
    "t800": Personality(
        greed=1.3,
        risk=0.4,
        aggression=1.4,
        expansion=1.2,
        devcards=0.45,
        trading=0.6,
        randomness=0.02,
    ),
    "human": Personality(
        greed=1.0,
        risk=1.0,
        aggression=0.8,
        expansion=1.0,
        devcards=1.0,
        trading=1.0,
        randomness=0.25,
    ),
    "merchant": Personality(
        greed=1.1,
        risk=0.8,
        aggression=0.4,
        expansion=0.8,
        devcards=1.2,
        trading=2.0,
        randomness=0.18,
    ),
    "chaos": Personality(
        greed=0.8,
        risk=2.0,
        aggression=1.2,
        expansion=1.0,
        devcards=1.8,
        trading=0.5,
        randomness=0.45,
    ),
}


class BotBrain:
    DICE_PROBABILITY = {
        2: 1,
        3: 2,
        4: 3,
        5: 4,
        6: 5,
        7: 0,
        8: 5,
        9: 4,
        10: 3,
        11: 2,
        12: 1,
        0: 0,
    }

    RESOURCES = [
        Resource.WOOD,
        Resource.BRICK,
        Resource.WHEAT,
        Resource.SHEEP,
        Resource.ORE,
    ]

    def __init__(self, player_id: int, game: Game, personality: Personality = None):
        self.pid = player_id
        self.game = game
        self.personality = personality or Personality()

    # ============================================================
    #  WEIGHTED CHOICE
    # ============================================================

    def _choose_weighted_action(self, candidates):
        if not candidates:
            return None

        randomness = self.personality.randomness
        weighted = []
        for action, params, utility in candidates:
            noise = random.uniform(-randomness, randomness)
            weighted.append((action, params, utility * (1.0 + noise)))

        weighted.sort(key=lambda x: x[2], reverse=True)
        top_n = min(3, len(weighted))
        return random.choice(weighted[:top_n])

    # ============================================================
    #  BASIC HELPERS
    # ============================================================

    def _player(self):
        return self.game.players[self.pid]

    def _can_afford(self, resources: dict, cost: dict) -> bool:
        return all(resources.get(r, 0) >= amt for r, amt in cost.items())

    def _resource_weight(self, res: Resource) -> float:
        """Чем меньше ресурса — тем он ценнее. Wheat/Ore чуть важнее."""
        p = self._player()
        have = p.resources.get(res, 0)

        base = 1.18 if res in (Resource.WHEAT, Resource.ORE) else 1.0

        if have <= 0:
            scarcity = 1.55
        elif have == 1:
            scarcity = 1.30
        elif have == 2:
            scarcity = 1.12
        else:
            scarcity = 1.0

        if self.game.turn <= 4 and res in (Resource.WOOD, Resource.BRICK):
            base *= 1.08

        return base * scarcity

    def _owned_production_resources(self) -> set[Resource]:
        owned = set()
        for v in self.game.map.vertices.values():
            if v.building_owner != self.pid:
                continue
            for hid in v.adjacent_hexes:
                tile = self.game.map.hexes[hid]
                if tile.resource != Resource.NONE:
                    owned.add(tile.resource)
        return owned

    # ============================================================
    #  VERTEX EVALUATION — два слоя
    # ============================================================

    def _vertex_production_score(self, vid: int) -> float:
        """
        Оценивает производственный потенциал вершины БЕЗ проверки занятости.
        Используется и для поселений, и для городов.
        """
        v = self.game.map.vertices[vid]
        resources = []
        score = 0.0

        for hid in v.adjacent_hexes:
            tile = self.game.map.hexes[hid]
            if tile.resource == Resource.NONE or tile.number_token <= 0:
                continue

            pip = self.DICE_PROBABILITY.get(tile.number_token, 0)
            if pip <= 0:
                continue

            resources.append(tile.resource)
            score += pip * self._resource_weight(tile.resource)

            if tile.number_token in (6, 8):
                score += 0.85
            elif tile.number_token in (5, 9):
                score += 0.45
            elif tile.number_token in (4, 10):
                score += 0.15

        if not resources:
            return 0.0

        unique = set(resources)
        score += len(unique) * 1.10
        score += len(resources) * 0.30
        score -= (len(resources) - len(unique)) * 0.35

        if v.is_port:
            if v.port_type is None:
                score += 2.6
            else:
                port_score = 3.5
                if v.port_type in unique:
                    port_score += 1.4
                score += port_score

        return score

    def _vertex_base_score(self, vid: int) -> float:
        """
        Оценка пустой вершины для нового поселения.
        Проверяет занятость и правило расстояния.
        """
        v = self.game.map.vertices[vid]
        if not v.is_empty:
            return -1e9

        for adj_vid in v.adjacent_vertices:
            if not self.game.map.vertices[adj_vid].is_empty:
                return -1e9

        return self._vertex_production_score(vid)

    def _city_score(self, vid: int) -> float:
        """
        Оценка вершины для улучшения до города.
        НЕ использует _vertex_base_score — там проверка is_empty.
        """
        v = self.game.map.vertices[vid]
        if v.building_owner != self.pid:
            return -1e9
        if v.building_type != BuildingType.SETTLEMENT:
            return -1e9

        prod = self._vertex_production_score(vid)
        # Город даёт +1 VP и удвоение производства
        return prod * 1.35 + 5.5

    def _vertex_forward_bonus(self, vid: int) -> float:
        """Насколько хороши соседние пустые вершины — потенциал роста."""
        bonuses = []
        for eid in self.game.map.vertices[vid].adjacent_edges:
            edge = self.game.map.edges[eid]
            if edge.road_owner is not None and edge.road_owner != self.pid:
                continue
            a, b = edge.vertices
            other = b if a == vid else a
            other_v = self.game.map.vertices[other]
            if (
                other_v.building_owner is not None
                and other_v.building_owner != self.pid
            ):
                continue
            if not other_v.is_empty:
                continue
            val = self._vertex_base_score(other)
            if val > 0:
                bonuses.append(val)

        bonuses.sort(reverse=True)
        return sum(bonuses[:2]) * 0.32

    def _second_settlement_bonus(self, vid: int) -> float:
        """Для второй стартовой точки — бонус за диверсификацию ресурсов."""
        owned = self._owned_production_resources()
        if not owned:
            return 0.0

        bonus = 0.0
        for hid in self.game.map.vertices[vid].adjacent_hexes:
            tile = self.game.map.hexes[hid]
            if tile.resource == Resource.NONE or tile.number_token <= 0:
                continue
            if tile.resource not in owned:
                bonus += 1.25 * self._resource_weight(tile.resource)
            else:
                bonus += 0.30
        return bonus

    def _vertex_score(self, vid: int, setup_round: int = 1) -> float:
        base = self._vertex_base_score(vid)
        if base < -1e8:
            return base
        score = base + self._vertex_forward_bonus(vid)
        if setup_round == 2:
            score += self._second_settlement_bonus(vid)
        return score

    # ============================================================
    #  ROAD EVALUATION
    # ============================================================

    def _is_buildable_vertex(self, vid: int) -> bool:
        v = self.game.map.vertices[vid]
        if not v.is_empty:
            return False
        return all(self.game.map.vertices[a].is_empty for a in v.adjacent_vertices)

    def _frontier_value(self, frontier: int, came_from: int) -> float:
        """
        Насколько ценно добраться до этой вершины:
        - можно ли строить прямо здесь
        - или через одну дорогу дальше
        """
        best = 0.0

        if self._is_buildable_vertex(frontier):
            prod = self._vertex_production_score(frontier)
            if prod > 0:
                best = max(best, prod + 4.0)

        frontier_v = self.game.map.vertices[frontier]
        for eid in frontier_v.adjacent_edges:
            e = self.game.map.edges[eid]
            if e.road_owner is not None and e.road_owner != self.pid:
                continue
            a, b = e.vertices
            nxt = b if a == frontier else a
            if nxt == came_from:
                continue
            nxt_v = self.game.map.vertices[nxt]
            if nxt_v.building_owner is not None and nxt_v.building_owner != self.pid:
                continue
            if self._is_buildable_vertex(nxt):
                prod = self._vertex_production_score(nxt)
                if prod > 0:
                    best = max(best, prod + 2.5)

        return best

    def _road_edge_score(self, eid: int) -> float:
        edge = self.game.map.edges[eid]
        if edge.road_owner is not None:
            return -1e9

        reachable = self.game._player_reachable_vertices(self.pid)
        a, b = edge.vertices

        if a not in reachable and b not in reachable:
            return -1e9

        best = -1e9

        for start, frontier in [(a, b), (b, a)]:
            if start not in reachable:
                continue
            frontier_v = self.game.map.vertices[frontier]
            if (
                frontier_v.building_owner is not None
                and frontier_v.building_owner != self.pid
            ):
                continue

            score = self._frontier_value(frontier, start)

            free_exits = sum(
                1
                for adj_eid in frontier_v.adjacent_edges
                if self.game.map.edges[adj_eid].road_owner is None
            )
            score += min(1.2, free_exits * 0.15)

            if score > best:
                best = score

        if best < 0:
            return -1e9

        # Внутренняя перемычка (оба конца уже достижимы) менее ценна
        if a in reachable and b in reachable:
            best *= 0.6

        return best * self.personality.expansion

    def _best_road_edge(self, targets: list[int]) -> tuple[Optional[int], float]:
        best_eid = None
        best_score = -1e9

        for eid in targets:
            s = self._road_edge_score(eid)
            if s > best_score:
                best_score = s
                best_eid = eid

        # Порог убран: берём любую дорогу с положительным score
        # Если даже лучшая дорога "ноль" — всё равно строим,
        # иначе бот может навсегда застрять без экспансии.
        if best_score < 0.0 and targets:
            # Возвращаем первую доступную как запасной вариант с низким score
            return targets[0], 0.5

        return best_eid, best_score

    # ============================================================
    #  BUILD PLAN
    # ============================================================

    def _dev_card_buy_utility(self, resources: dict, targets: dict) -> float:
        """
        Динамическая полезность покупки карты.
        Снижается если можно строить города/поселения, растёт в лейте.
        """
        player = self._player()
        vp = self.game.get_victory_points(self.pid, public=False)
        non_vp_cards = sum(
            1 for c in player.dev_cards if c.card_type != DevCardType.VICTORY_POINT
        )

        utility = 0.9

        # В лейте карты ценнее (рыцари, VP)
        if vp >= 7:
            utility += 1.5
        elif vp >= 5:
            utility += 0.6

        # Если нет куда строиться — карты разумнее
        has_city_targets = bool(targets.get("build_city_vertices"))
        has_settlement_targets = bool(targets.get("build_settlement_vertices"))
        if not has_city_targets and not has_settlement_targets:
            utility += 0.7

        # Много карт на руках — не жадничаем
        utility -= non_vp_cards * 0.25
        utility = max(0.1, utility)

        # Если близко до города — резко снижаем приоритет карт
        city_missing = sum(
            max(COST_CITY.get(r, 0) - resources.get(r, 0), 0) for r in COST_CITY
        )
        if has_city_targets and city_missing <= 2:
            utility *= 0.3

        utility *= self.personality.devcards
        return utility

    def _best_build_plan(
        self,
        resources: dict,
        targets: dict,
        include_dev_card: bool = True,
    ) -> tuple[str, dict, float]:
        """
        Возвращает (action, params, utility) лучшего доступного плана.
        include_dev_card=False — для оценки в контексте торговли
        (чтобы бот не торговал ради покупки карты).
        """
        plans = []

        # Город
        if targets.get("build_city_vertices"):
            best_vid, best_score = None, -1e9
            for vid in targets["build_city_vertices"]:
                s = self._city_score(vid)
                if s > best_score:
                    best_score, best_vid = s, vid
            if best_vid is not None and self._can_afford(resources, COST_CITY):
                plans.append(("build_city", {"vertex_id": best_vid}, best_score))

        # Поселение
        if targets.get("build_settlement_vertices"):
            setup_round = 2 if self.game.setup_index >= len(self.game.players) else 1
            best_vid, best_score = None, -1e9
            for vid in targets["build_settlement_vertices"]:
                s = self._vertex_score(vid, setup_round=setup_round)
                if s > best_score:
                    best_score, best_vid = s, vid
            if best_vid is not None and self._can_afford(resources, COST_SETTLEMENT):
                plans.append(("build_settlement", {"vertex_id": best_vid}, best_score))

        # Дорога — НЕ занижаем score дополнительно
        if targets.get("build_road_edges"):
            best_eid, best_score = self._best_road_edge(targets["build_road_edges"])
            if best_eid is not None and self._can_afford(resources, COST_ROAD):
                plans.append(("build_road", {"edge_id": best_eid}, best_score))

        # Карта развития — динамическая оценка
        if include_dev_card:
            if self._can_afford(resources, COST_DEV_CARD) and self.game.dev_card_deck:
                util = self._dev_card_buy_utility(resources, targets)
                if util > 0:
                    plans.append(("buy_dev_card", {}, util))

        if not plans:
            return None, {}, 0.0

        return max(plans, key=lambda x: x[2])

    # ============================================================
    #  BANK TRADE
    # ============================================================

    def _best_bank_trade(self, current_utility: float, targets: dict) -> Optional[dict]:
        """
        Ищем одну банковскую сделку, которая заметно улучшит лучший план.
        Карта развития НЕ считается целевым планом при оценке торговли.
        """
        player = self._player()
        best_trade = None
        best_gain = 0.0

        for give_r in self.RESOURCES:
            rate = self.game._bank_trade_rate(self.pid, give_r)
            if player.resources.get(give_r, 0) < rate:
                continue

            for recv_r in self.RESOURCES:
                if recv_r == give_r:
                    continue

                temp = dict(player.resources)
                temp[give_r] = temp.get(give_r, 0) - rate
                temp[recv_r] = temp.get(recv_r, 0) + 1

                # include_dev_card=False — не торгуем ради карты
                _, _, util = self._best_build_plan(
                    temp, targets, include_dev_card=False
                )
                gain = util - current_utility

                if gain > best_gain:
                    best_gain = gain
                    best_trade = {"give": give_r.value, "receive": recv_r.value}

        # Порог снижен: торгуем если хоть немного полезно
        if best_gain >= 1.0:
            return best_trade

        return None

    # ============================================================
    #  PIRATE / VICTIMS
    # ============================================================

    def _best_pirate_hex(self, legal_hexes: list[int]) -> tuple[Optional[int], float]:
        best_hid = None
        best_score = -1e9

        for hid in legal_hexes:
            tile = self.game.map.hexes.get(hid)
            if tile is None:
                continue

            score = 0.0
            own_hits = 0
            enemy_hits = 0

            for v in self.game.map.vertices.values():
                if hid not in v.adjacent_hexes or v.building_owner is None:
                    continue
                owner = v.building_owner
                if owner == self.pid:
                    own_hits += 1
                else:
                    enemy_hits += 1
                    score += self.game.get_victory_points(owner, public=True) * 0.8
                    score += self.game.players[owner].total_resources * 0.15

            score += self.DICE_PROBABILITY.get(tile.number_token, 0) * 1.6

            if tile.number_token in (6, 8):
                score += 2.0
            elif tile.number_token in (5, 9):
                score += 1.0

            if tile.terrain == TerrainType.RUINS:
                score += 0.8

            score += enemy_hits * 2.5
            score *= self.personality.aggression
            score -= own_hits * 8.0

            if score > best_score:
                best_score = score
                best_hid = hid

        return best_hid, best_score

    def _best_pirate_victim(self, victims: list[int]) -> Optional[int]:
        valid = [v for v in victims if self.game.players[v].total_resources > 0]
        if not valid:
            return None
        return max(
            valid,
            key=lambda v: (
                self.game.players[v].total_resources,
                self.game.get_victory_points(v, public=True),
            ),
        )

    def _legal_pirate_hexes_now(self) -> list[int]:
        """Цели для пирата в фазе MAIN (для оценки Knight)."""
        player = self._player()
        return [hid for hid in player.revealed_hexes if hid != self.game.pirate_hex]

    def _legal_road_edges_ignore_cost(self) -> list[int]:
        """Доступные дороги без учёта ресурсов (для оценки Road Building)."""
        player = self._player()
        if player.roads_left <= 0:
            return []
        return [
            eid
            for eid, edge in self.game.map.edges.items()
            if edge.road_owner is None and self.game._is_road_connected(self.pid, eid)
        ]

    # ============================================================
    #  DEV CARD SELECTION
    # ============================================================

    def _choose_year_of_plenty(self, targets: dict, current_best_utility: float):
        player = self._player()
        best_params = None
        best_utility = current_best_utility

        for r1 in self.RESOURCES:
            for r2 in self.RESOURCES:
                temp = dict(player.resources)
                temp[r1] = temp.get(r1, 0) + 1
                temp[r2] = temp.get(r2, 0) + 1
                # include_dev_card=False — не берём ресурсы ради карты
                _, _, util = self._best_build_plan(
                    temp, targets, include_dev_card=False
                )
                if util > best_utility:
                    best_utility = util
                    best_params = {"resource1": r1.value, "resource2": r2.value}

        return best_params, best_utility

    def _choose_monopoly_resource(self):
        best_r = None
        best_score = 0.0

        for r in self.RESOURCES:
            total = sum(
                p.resources.get(r, 0)
                for p in self.game.players
                if p.player_id != self.pid
            )
            score = total * self._resource_weight(r) * self.personality.greed
            if r in (Resource.WHEAT, Resource.ORE):
                score *= 1.15
            if score > best_score:
                best_score = score
                best_r = r

        return best_r, best_score

    def _best_explorer_hex(self):
        player = self._player()
        best_hid = None
        best_score = -1e9

        for hid, tile in self.game.map.hexes.items():
            if hid in player.revealed_hexes:
                continue
            score = self.DICE_PROBABILITY.get(tile.number_token, 0) * 1.8
            if tile.terrain == TerrainType.RUINS:
                score += 4.0
            if tile.number_token in (6, 8):
                score += 2.5
            elif tile.number_token in (5, 9):
                score += 1.2
            if score > best_score:
                best_score = score
                best_hid = hid

        return best_hid, best_score

    def _pirate_hunter_utility(self) -> float:
        if self.game.pirate_hex is None:
            return 0.0
        tile = self.game.map.hexes.get(self.game.pirate_hex)
        if tile is None or tile.terrain == TerrainType.DESERT:
            return 0.0

        score = 0.0
        for v in self.game.map.vertices.values():
            if self.game.pirate_hex not in v.adjacent_hexes or v.building_owner is None:
                continue
            owner = v.building_owner
            if owner == self.pid:
                # Исправлено: используем _vertex_production_score, не _vertex_base_score
                score += self._vertex_production_score(v.vertex_id) * 0.8
            else:
                score += self.game.get_victory_points(owner, public=True) * 0.6
                score += self.game.players[owner].total_resources * 0.1

        return score

    def _rebellion_utility(self) -> float:
        score = 0.0
        for p in self.game.players:
            if p.player_id != self.pid:
                score += p.total_resources * 0.5
        return score

    def _sanctions_utility(self) -> float:
        me_vp = self.game.get_victory_points(self.pid, public=True)
        best = 0.0
        for p in self.game.players:
            if p.player_id == self.pid:
                continue
            vp = self.game.get_victory_points(p.player_id, public=True)
            score = 0.0
            if vp >= me_vp:
                score += (vp - me_vp + 1) * 2.0
            score += p.total_resources * 0.2
            if score > best:
                best = score
        return best

    def _best_dev_card_action(self, current_best_utility: float, targets: dict):
        """
        Выбирает лучшую карту для розыгрыша прямо сейчас.
        Возвращает (action, params, utility) или None.
        """
        if self._player().dev_card_played_this_turn:
            return None

        player = self._player()
        candidates = []

        playable = [
            c
            for c in player.dev_cards
            if c.card_type != DevCardType.VICTORY_POINT
            and self.game.turn >= c.playable_from_turn
        ]

        for c in playable:
            ct = c.card_type

            if ct == DevCardType.KNIGHT:
                # Используем свой helper, не targets (там пусто в MAIN)
                pirate_targets = self._legal_pirate_hexes_now()
                hid, threat = self._best_pirate_hex(pirate_targets)
                if hid is not None and threat >= 5.0:
                    candidates.append(
                        (
                            "play_dev_card",
                            {"card_type": ct.value},
                            threat + 2.0,
                        )
                    )

            elif ct == DevCardType.ROAD_BUILDING:
                # Используем свой helper без учёта ресурсов
                road_targets = self._legal_road_edges_ignore_cost()
                road_scores = sorted(
                    [
                        self._road_edge_score(eid)
                        for eid in road_targets
                        if self._road_edge_score(eid) > 0
                    ],
                    reverse=True,
                )
                if road_scores:
                    util = sum(road_scores[:2]) + 3.0
                    if util > current_best_utility + 1.0:
                        candidates.append(
                            ("play_dev_card", {"card_type": ct.value}, util)
                        )

            elif ct == DevCardType.YEAR_OF_PLENTY:
                params, util = self._choose_year_of_plenty(
                    targets, current_best_utility
                )
                if params is not None:
                    candidates.append(
                        (
                            "play_dev_card",
                            {"card_type": ct.value, **params},
                            util + 0.2,
                        )
                    )

            elif ct == DevCardType.MONOPOLY:
                res, util = self._choose_monopoly_resource()
                if res is not None and util >= 3.5:
                    candidates.append(
                        (
                            "play_dev_card",
                            {"card_type": ct.value, "resource": res.value},
                            util + 0.5,
                        )
                    )

            elif ct == DevCardType.EXPLORER:
                hid, util = self._best_explorer_hex()
                if hid is not None and util >= 4.0:
                    candidates.append(
                        (
                            "play_dev_card",
                            {"card_type": ct.value, "hex_id": hid},
                            util,
                        )
                    )

            elif ct == DevCardType.PIRATE_HUNTER:
                util = self._pirate_hunter_utility()
                if util >= 5.0:
                    candidates.append(("play_dev_card", {"card_type": ct.value}, util))

            elif ct == DevCardType.REBELLION:
                util = self._rebellion_utility()
                if util >= 4.0:
                    candidates.append(("play_dev_card", {"card_type": ct.value}, util))

            elif ct == DevCardType.SANCTIONS:
                util = self._sanctions_utility()
                if util >= 4.0:
                    candidates.append(("play_dev_card", {"card_type": ct.value}, util))

            elif ct == DevCardType.TRADE_AGREEMENT:
                # Проверяем, даст ли 2:1 обмен доступ к новой постройке
                best_util = 0.0
                for give_r in self.RESOURCES:
                    if player.resources.get(give_r, 0) < 2:
                        continue
                    for recv_r in self.RESOURCES:
                        if recv_r == give_r:
                            continue
                        temp = dict(player.resources)
                        temp[give_r] = temp.get(give_r, 0) - 2
                        temp[recv_r] = temp.get(recv_r, 0) + 1
                        _, _, util = self._best_build_plan(
                            temp, targets, include_dev_card=False
                        )
                        if util > best_util:
                            best_util = util
                if best_util >= current_best_utility + 2.0:
                    candidates.append(
                        (
                            "play_dev_card",
                            {"card_type": ct.value},
                            best_util,
                        )
                    )

        if not candidates:
            return None

        # Применяем personality multiplier
        adjusted = [(a, p, u * self.personality.devcards) for a, p, u in candidates]
        return max(adjusted, key=lambda x: x[2])

    # ============================================================
    #  MAIN DECISION
    # ============================================================

    def decide(self) -> tuple[str, dict]:
        phase = self.game.phase

        if phase == GamePhase.SETUP:
            return self._decide_setup_settlement()
        if phase == GamePhase.SETUP_ROAD:
            return self._decide_setup_road()
        if phase == GamePhase.ROLL:
            return "roll_dice", {}
        if phase == GamePhase.DISCARD:
            return self._decide_discard()
        if phase == GamePhase.PIRATE_MOVE:
            return self._decide_pirate_move()
        if phase == GamePhase.PIRATE_STEAL:
            return self._decide_pirate_steal()
        if phase == GamePhase.MAIN:
            return self._decide_main()

        return "end_turn", {}

    def _decide_setup_settlement(self):
        targets = self.game._get_legal_targets(self.pid).get(
            "setup_settlement_vertices", []
        )
        if not targets:
            return "end_turn", {}

        setup_round = 2 if self.game.setup_index >= len(self.game.players) else 1
        best_vid, best_score = None, -1e9
        for vid in targets:
            s = self._vertex_score(vid, setup_round=setup_round)
            if s > best_score:
                best_score, best_vid = s, vid

        if best_vid is None:
            best_vid = targets[0]

        return "setup_settlement", {"vertex_id": best_vid}

    def _decide_setup_road(self):
        targets = self.game._get_legal_targets(self.pid).get("setup_road_edges", [])
        if not targets:
            return "end_turn", {}

        # Ищем дорогу, ведущую к лучшему соседнему перекрёстку
        best_eid = targets[0]
        best_score = -1e9

        for eid in targets:
            edge = self.game.map.edges[eid]
            for vid in edge.vertices:
                if vid == self.game.last_setup_vertex:
                    continue
                s = self._vertex_production_score(vid)
                if s > best_score:
                    best_score = s
                    best_eid = eid

        return "setup_road", {"edge_id": best_eid}

    def _decide_pirate_move(self):
        targets = self.game._get_legal_targets(self.pid).get("move_pirate_hexes", [])
        if not targets:
            return "end_turn", {}

        hid, _ = self._best_pirate_hex(targets)
        if hid is None:
            hid = targets[0]

        return "move_pirate", {"hex_id": hid}

    def _decide_pirate_steal(self):
        victims = self.game.pending_pirate_victims
        if not victims:
            return "end_turn", {}

        victim_id = self._best_pirate_victim(victims)
        if victim_id is None:
            return "end_turn", {}

        return "choose_pirate_victim", {"victim_id": victim_id}

    def _decide_discard(self):
        player = self._player()
        count = self.game.pending_discards.get(self.pid, 0)
        discards = {r.value: 0 for r in self.RESOURCES}

        remaining = count
        while remaining > 0:
            # Сбрасываем самый избыточный ресурс (много и мало ценен)
            best_res = max(
                self.RESOURCES,
                key=lambda r: (
                    (player.resources.get(r, 0) - discards[r.value])
                    / self._resource_weight(r)
                ),
            )
            discards[best_res.value] += 1
            remaining -= 1

        clean = {k: v for k, v in discards.items() if v > 0}
        return "discard", {"discards": clean}

    def _decide_main(self):
        player = self._player()
        targets = self.game._get_legal_targets(self.pid)
        actions = self.game._get_available_actions(self.pid)

        # 1. Бесплатные дороги
        if player.free_roads_pending > 0 and targets.get("build_road_edges"):
            eid, _ = self._best_road_edge(targets["build_road_edges"])
            if eid is None:
                eid = targets["build_road_edges"][0]
            return "build_free_road", {"edge_id": eid}

        # 2. Лучший обычный план
        best_action, best_params, best_utility = self._best_build_plan(
            player.resources, targets
        )

        # 3. Dev card — только если сильно лучше текущего плана
        best_dev = None
        if "play_dev_card" in actions and not player.dev_card_played_this_turn:
            best_dev = self._best_dev_card_action(best_utility, targets)

        if best_dev is not None:
            _, _, dev_utility = best_dev
            # Dev card должна быть заметно лучше — порог снижен до +2.0
            if dev_utility > best_utility + 2.0:
                return best_dev[0], best_dev[1]

        # 4. Торговля с банком — только если открывает реальное строительство
        if "trade_bank" in actions:
            # Считаем current_utility без dev_card для честного сравнения
            _, _, base_utility = self._best_build_plan(
                player.resources, targets, include_dev_card=False
            )
            trade = self._best_bank_trade(base_utility, targets)
            if trade is not None:
                return "trade_bank", trade

        # 5. Есть нормальный build
        if best_action is not None:
            return best_action, best_params

        # 6. Dev card как второй выбор (если первый план пустой)
        if best_dev is not None:
            return best_dev[0], best_dev[1]

        # 7. Купить карту если совсем нечего делать
        if "buy_dev_card" in actions:
            return "buy_dev_card", {}

        return "end_turn", {}

    # ============================================================
    #  TRADE RESPONSE
    # ============================================================

    def respond_to_trade(self, offer) -> bool:
        if offer.from_player == self.pid:
            return False

        player = self._player()

        if self.game.turn < player.sanctioned_until_turn:
            return False

        # Есть ли ресурсы отдать?
        for r, amt in offer.want.items():
            if player.resources.get(r, 0) < amt:
                return False

        # Симулируем обмен
        temp = dict(player.resources)
        for r, amt in offer.want.items():
            temp[r] = temp.get(r, 0) - amt
        for r, amt in offer.give.items():
            temp[r] = temp.get(r, 0) + amt

        targets = self.game._get_legal_targets(self.pid)

        _, _, current_plan = self._best_build_plan(
            player.resources, targets, include_dev_card=False
        )
        _, _, new_plan = self._best_build_plan(temp, targets, include_dev_card=False)

        if new_plan > current_plan + 1.5:
            return True

        # Или если обмен улучшает ресурсный профиль по весам
        current_value = sum(
            player.resources.get(r, 0) * self._resource_weight(r)
            for r in self.RESOURCES
        )
        new_value = sum(
            temp.get(r, 0) * self._resource_weight(r) for r in self.RESOURCES
        )

        gained_good = any(
            self._resource_weight(r) >= 1.15 and amt > 0
            for r, amt in offer.give.items()
        )

        if gained_good and new_value >= current_value - 0.25:
            return True

        return False
