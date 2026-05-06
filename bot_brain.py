import random

from game_engine import BuildingType, DevCardType, Game, GamePhase, Resource


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

    def __init__(self, player_id: int, game: Game):
        self.pid = player_id
        self.game = game

    def decide(self) -> tuple[str, dict]:
        """Главный метод принятия решений. Возвращает (action, params)"""
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

    def _vertex_score(self, vid: int) -> float:
        """Оценивает "крутость" перекрестка по вероятности выпадения ресурсов"""
        vertex = self.game.map.vertices[vid]
        score = 0.0
        for hid in vertex.adjacent_hexes:
            tile = self.game.map.hexes.get(hid)
            if tile and tile.resource != Resource.NONE:
                score += self.DICE_PROBABILITY.get(tile.number_token, 0)
        if vertex.is_port:
            score += 2.0
        return score

    def _edge_score(self, eid: int) -> float:
        """Оценивает полезность дороги: насколько ценны свободные места на её концах"""
        edge = self.game.map.edges[eid]
        score = 0.0
        for vid in edge.vertices:
            vertex = self.game.map.vertices[vid]
            # Дорога имеет смысл, только если ведет к пустой вершине (где можно построиться)
            if vertex.is_empty:
                score += self._vertex_score(vid)
        return score

    def _decide_setup_settlement(self):
        targets = self.game._get_legal_targets(self.pid).get(
            "setup_settlement_vertices", []
        )
        if not targets:
            return "end_turn", {}

        # Выбираем топ-3 лучших места и берем одно случайно (чтобы бот не играл всегда одинаково)
        scored = sorted(
            [(vid, self._vertex_score(vid)) for vid in targets],
            key=lambda x: x[1],
            reverse=True,
        )
        best_vid = random.choice(scored[:3])[0] if len(scored) >= 3 else scored[0][0]
        return "setup_settlement", {"vertex_id": best_vid}

    def _decide_setup_road(self):
        targets = self.game._get_legal_targets(self.pid).get("setup_road_edges", [])
        if not targets:
            return "end_turn", {}

        # Выбираем дорогу, которая ведет к самой "жирной" свободной точке
        scored = sorted(
            [(eid, self._edge_score(eid)) for eid in targets],
            key=lambda x: x[1],
            reverse=True,
        )
        return "setup_road", {"edge_id": scored[0][0]}

    def _decide_pirate_move(self):
        targets = self.game._get_legal_targets(self.pid).get("move_pirate_hexes", [])
        if not targets:
            return "end_turn", {}

        # Бот ищет гекс с наибольшей вероятностью, где стоят чужие здания, но нет его собственных
        best_hex = targets[0]
        best_score = -1

        for hid in targets:
            tile = self.game.map.hexes.get(hid)
            if not tile:
                continue

            score = self.DICE_PROBABILITY.get(tile.number_token, 0)
            has_enemies = False
            has_me = False

            for vid, vertex in self.game.map.vertices.items():
                if hid in vertex.adjacent_hexes and vertex.building_owner is not None:
                    if vertex.building_owner == self.pid:
                        has_me = True
                    else:
                        has_enemies = True

            if has_me:
                score -= 100  # Не вредим себе
            if has_enemies:
                score += 10  # Вредим врагам

            if score > best_score:
                best_score = score
                best_hex = hid

        return "move_pirate", {"hex_id": best_hex}

    def _decide_pirate_steal(self):
        victims = self.game.pending_pirate_victims
        if not victims:
            return "end_turn", {}
        # Бот ворует у того, у кого больше всего публичных очков
        best_victim = max(
            victims, key=lambda v: self.game.get_victory_points(v, public=True)
        )
        return "choose_pirate_victim", {"victim_id": best_victim}

    def _decide_discard(self):
        player = self.game.players[self.pid]
        count = self.game.pending_discards.get(self.pid, 0)
        discards = {}

        # Сбрасываем те ресурсы, которых у нас больше всего
        pool = [r for r, amt in player.resources.items() for _ in range(amt)]
        pool.sort(key=lambda r: player.resources.get(r, 0), reverse=True)

        for r in pool[:count]:
            discards[r.value] = discards.get(r.value, 0) + 1

        return "discard", {"discards": discards}

    def _decide_main(self):
        actions = self.game._get_available_actions(self.pid)
        targets = self.game._get_legal_targets(self.pid)
        player = self.game.players[self.pid]

        # 1. Бесплатные дороги
        if "build_free_road" in actions and targets["build_road_edges"]:
            scored = sorted(
                [(eid, self._edge_score(eid)) for eid in targets["build_road_edges"]],
                key=lambda x: x[1],
                reverse=True,
            )
            return "build_free_road", {"edge_id": scored[0][0]}

        # 2. Карты развития
        if "play_dev_card" in actions:
            playable = [
                c
                for c in player.dev_cards
                if c.card_type != DevCardType.VICTORY_POINT
                and self.game.turn >= c.playable_from_turn
            ]
            for c in playable:
                if c.card_type == DevCardType.KNIGHT:
                    return "play_dev_card", {"card_type": "knight"}

                # Монополия: воруем ресурс, которого нам не хватает
                elif c.card_type == DevCardType.MONOPOLY:
                    missing = [
                        r
                        for r in [
                            Resource.WOOD,
                            Resource.BRICK,
                            Resource.WHEAT,
                            Resource.SHEEP,
                            Resource.ORE,
                        ]
                        if player.resources.get(r, 0) == 0
                    ]
                    target_res = missing[0] if missing else Resource.ORE
                    return "play_dev_card", {
                        "card_type": "monopoly",
                        "resource": target_res.value,
                    }

                # Год изобилия: берем то, чего нет
                elif c.card_type == DevCardType.YEAR_OF_PLENTY:
                    missing = [
                        r
                        for r in [
                            Resource.WOOD,
                            Resource.BRICK,
                            Resource.WHEAT,
                            Resource.SHEEP,
                            Resource.ORE,
                        ]
                        if player.resources.get(r, 0) == 0
                    ]
                    r1 = missing[0] if len(missing) > 0 else Resource.WOOD
                    r2 = missing[1] if len(missing) > 1 else Resource.BRICK
                    return "play_dev_card", {
                        "card_type": "year_of_plenty",
                        "resource1": r1.value,
                        "resource2": r2.value,
                    }

                # Исследователь (Мод тумана войны)
                elif c.card_type == DevCardType.EXPLORER:
                    unrevealed = [
                        hid
                        for hid in self.game.map.hexes
                        if hid not in player.revealed_hexes
                    ]
                    if unrevealed:
                        return "play_dev_card", {
                            "card_type": "explorer",
                            "hex_id": random.choice(unrevealed),
                        }

                # Агрессивные/Дипломатические моды играем при любой возможности
                elif c.card_type in (
                    DevCardType.PIRATE_HUNTER,
                    DevCardType.ANCIENT_MAP,
                    DevCardType.REBELLION,
                    DevCardType.TRADE_AGREEMENT,
                    DevCardType.SANCTIONS,
                ):
                    return "play_dev_card", {"card_type": c.card_type.value}

        # 3. Город (улучшаем самое прибыльное поселение)
        if "build_city" in actions and targets["build_city_vertices"]:
            scored = sorted(
                [
                    (vid, self._vertex_score(vid))
                    for vid in targets["build_city_vertices"]
                ],
                key=lambda x: x[1],
                reverse=True,
            )
            return "build_city", {"vertex_id": scored[0][0]}

        # 4. Поселение
        if "build_settlement" in actions and targets["build_settlement_vertices"]:
            scored = sorted(
                [
                    (vid, self._vertex_score(vid))
                    for vid in targets["build_settlement_vertices"]
                ],
                key=lambda x: x[1],
                reverse=True,
            )
            return "build_settlement", {"vertex_id": scored[0][0]}

        # 5. Купить карту развития (если ресурсов много, а строить негде)
        if "buy_dev_card" in actions:
            return "buy_dev_card", {}

        # 6. Дорога
        if "build_road" in actions and targets["build_road_edges"]:
            # Бот строит дорогу только если у него мало дорог, чтобы не тратить ресурсы впустую
            if player.roads_left > 10:
                scored = sorted(
                    [
                        (eid, self._edge_score(eid))
                        for eid in targets["build_road_edges"]
                    ],
                    key=lambda x: x[1],
                    reverse=True,
                )
                return "build_road", {"edge_id": scored[0][0]}

        # 7. Торговля с банком
        if "trade_bank" in actions:
            for give_r in [
                Resource.WOOD,
                Resource.BRICK,
                Resource.WHEAT,
                Resource.SHEEP,
                Resource.ORE,
            ]:
                rate = self.game._bank_trade_rate(self.pid, give_r)
                if player.resources.get(give_r, 0) >= rate:
                    # Ищем ресурс, которого у нас 0
                    for want_r in [
                        Resource.WOOD,
                        Resource.BRICK,
                        Resource.WHEAT,
                        Resource.SHEEP,
                        Resource.ORE,
                    ]:
                        if player.resources.get(want_r, 0) == 0:
                            return "trade_bank", {
                                "give": give_r.value,
                                "receive": want_r.value,
                            }

        return "end_turn", {}

    def respond_to_trade(self, offer) -> bool:
        """Бот принимает обмен, только если он ОЧЕНЬ выгоден (ему отдают то, чего у него нет)"""
        if offer.from_player == self.pid:
            return False
        player = self.game.players[self.pid]

        # Проверяем, есть ли у бота то, что просят
        for r, amt in offer.want.items():
            if player.resources.get(r, 0) < amt:
                return False

        # Соглашаемся, только если получаем ресурс, которого у нас нет
        for r, amt in offer.give.items():
            if player.resources.get(r, 0) == 0:
                return True
        return False
