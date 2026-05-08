#!/usr/bin/env python3
"""
Колонизаторы: Terra Incognita — WebSocket Сервер + Статистика
"""

import asyncio
import datetime
import html
import json
import os
import secrets
import string
import sys
import traceback
from http import HTTPStatus
from pathlib import Path

from bot_brain import (
    BOT_PERSONALITIES,
    BotBrain,
)

try:
    import websockets
    from websockets.asyncio.server import serve
except ImportError:
    print("Установите websockets: pip install websockets")
    raise

from game_engine import Game, GamePhase

STATIC_DIR = Path(__file__).parent / "static"
HTTP_PORT = 8080
WS_PORT = 8765
STATS_FILE = Path("stats.json")

rooms: dict[str, Game] = {}
connections: dict = {}
room_connections: dict[str, dict[int, object]] = {}
room_cleanup_tasks: dict[str, asyncio.Task] = {}

stats_lock = asyncio.Lock()
room_locks: dict[str, asyncio.Lock] = {}


def safe_int(value, default, min_val=None, max_val=None):
    try:
        res = int(value)
        if min_val is not None:
            res = max(res, min_val)
        if max_val is not None:
            res = min(res, max_val)
        return res
    except (TypeError, ValueError):
        return default


# --- ПРОСТАЯ СТАТИСТИКА БЕЗ БАЗЫ ДАННЫХ ---
async def update_stats(event_type: str):
    """event_type может быть 'games_created' или 'games_finished'"""
    async with stats_lock:
        stats = {}
        if STATS_FILE.exists():
            try:
                stats = json.loads(STATS_FILE.read_text(encoding="utf-8"))
            except:
                pass

        today = str(datetime.date.today())
        month = today[:7]

        if "total" not in stats:
            stats["total"] = {"games_created": 0, "games_finished": 0}
        if month not in stats:
            stats[month] = {"games_created": 0, "games_finished": 0}
        if today not in stats:
            stats[today] = {"games_created": 0, "games_finished": 0}

        stats["total"][event_type] += 1
        stats[month][event_type] += 1
        stats[today][event_type] += 1

        STATS_FILE.write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def generate_room_id():
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


async def send_error(ws, msg: str):
    try:
        await ws.send(json.dumps({"type": "error", "msg": msg}, ensure_ascii=False))
    except Exception:
        pass


async def broadcast_state(room_id: str):
    game = rooms.get(room_id)
    if not game:
        return

    if game.phase == GamePhase.FINISHED and not getattr(game, "stats_saved", False):
        game.stats_saved = True
        await update_stats("games_finished")

    conns = room_connections.get(room_id, {})
    dead_conns = []

    for pid, ws_conn in list(conns.items()):
        try:
            state = game.get_state_for_player(pid)
            await ws_conn.send(
                json.dumps({"type": "state", "data": state}, ensure_ascii=False)
            )
        except Exception:
            dead_conns.append(pid)

    for pid in dead_conns:
        room_connections[room_id].pop(pid, None)

    await maybe_trigger_bot(room_id)


async def delayed_room_cleanup(
    room_id: str, delay: float = 300.0
):  # 5 минут на реконнект
    await asyncio.sleep(delay)
    conns = room_connections.get(room_id, {})
    if not conns:
        rooms.pop(room_id, None)
        room_connections.pop(room_id, None)
        room_locks.pop(room_id, None)
        print(f"  🗑️ Комната {room_id} удалена (таймаут)")
    room_cleanup_tasks.pop(room_id, None)


def cancel_room_cleanup(room_id: str):
    task = room_cleanup_tasks.pop(room_id, None)
    if task:
        task.cancel()


def schedule_room_cleanup(room_id: str):
    cancel_room_cleanup(room_id)
    task = asyncio.create_task(delayed_room_cleanup(room_id))
    room_cleanup_tasks[room_id] = task


# --- ЗАЩИТА ОТ ДВОЙНЫХ ЗАПУСКОВ БОТА ---
active_bot_tasks = set()


async def process_bot_turn(room_id: str, bot_pid: int):
    """Асинхронная корутина, которая управляет ботом"""
    task_id = f"{room_id}_{bot_pid}"

    # Если бот уже думает в другом потоке, не мешаем ему
    if task_id in active_bot_tasks:
        return

    active_bot_tasks.add(task_id)
    try:
        game = rooms.get(room_id)
        if not game or game.phase in (GamePhase.LOBBY, GamePhase.FINISHED):
            return
        if bot_pid not in game.bot_pids:
            return

        # Бот может сделать до 15 действий за один ход (построить дорогу, поселение, бросить кубик...)
        for _ in range(15):
            needs_action = False
            if game.current_player_idx == bot_pid and game.phase in (
                GamePhase.SETUP,
                GamePhase.SETUP_ROAD,
                GamePhase.ROLL,
                GamePhase.MAIN,
                GamePhase.PIRATE_MOVE,
                GamePhase.PIRATE_STEAL,
            ):
                needs_action = True
            elif game.phase == GamePhase.DISCARD and bot_pid in game.pending_discards:
                needs_action = True

            if not needs_action:
                break

            print(
                f"🤖 [КОМНАТА {room_id}] Бот {game.players[bot_pid].name} думает... (Фаза: {game.phase.value})"
            )

            # Пауза, чтобы люди видели, что делает бот
            await asyncio.sleep(1.5)

            # Перехватываем ошибки внутри мозга бота
            bot_name = game.players[bot_pid].name

            if "T-800" in bot_name:
                personality = BOT_PERSONALITIES["t800"]

            elif "R2D2" in bot_name:
                personality = BOT_PERSONALITIES["merchant"]

            elif "C3PO" in bot_name:
                personality = BOT_PERSONALITIES["human"]

            elif "Валл-И" in bot_name:
                personality = BOT_PERSONALITIES["chaos"]

            else:
                personality = BOT_PERSONALITIES["human"]

            brain = BotBrain(
                bot_pid,
                game,
                personality=personality,
            )
            try:
                action, params = brain.decide()
                print(f"🤖 [КОМНАТА {room_id}] Бот решил: {action} {params}")
            except Exception as e:
                print(f"❌ ОШИБКА В МОЗГАХ БОТА {bot_pid}: {e}")
                traceback.print_exc()  # Выведет точную строку ошибки в консоль
                action, params = "end_turn", {}

            # Выполняем действие
            lock = room_locks.setdefault(room_id, asyncio.Lock())
            async with lock:
                result = handle_game_action(game, bot_pid, action, params)

                if result.get("error"):
                    print(
                        f"⚠️ ОШИБКА ДЕЙСТВИЯ БОТА: {result['error']} (Действие: {action})"
                    )
                    # Если бот застрял - принудительно пасуем
                    if action != "end_turn" and game.phase == GamePhase.MAIN:
                        handle_game_action(game, bot_pid, "end_turn", {})
                        break

            # Рассылаем результат всем игрокам
            await broadcast_state(room_id)

            if action == "end_turn":
                break

    finally:
        active_bot_tasks.discard(task_id)


async def maybe_trigger_bot(room_id: str):
    """Запускает бота, если наступила его очередь"""
    game = rooms.get(room_id)
    if not game:
        return

    # 1. Основной ход бота
    if game.current_player_idx in game.bot_pids:
        asyncio.create_task(process_bot_turn(room_id, game.current_player_idx))

    # 2. Сброс карт ботом (при выпадении 7)
    if game.phase == GamePhase.DISCARD:
        for bot_pid in game.bot_pids:
            if bot_pid in game.pending_discards:
                asyncio.create_task(process_bot_turn(room_id, bot_pid))

    # 3. Ответ бота на торговлю
    if getattr(game, "active_trade_offer", None):
        offer = game.active_trade_offer
        for bot_pid in game.bot_pids:
            if bot_pid != offer.from_player and bot_pid not in offer.rejected_by:
                # Оборачиваем ответ в отдельную мини-корутину
                async def bot_trade_response(b_pid, b_offer):
                    await asyncio.sleep(1.5)
                    lock = room_locks.setdefault(room_id, asyncio.Lock())
                    async with lock:
                        if (
                            game.active_trade_offer == b_offer
                        ):  # Если оффер еще актуален
                            brain = BotBrain(b_pid, game)
                            accept = brain.respond_to_trade(b_offer)
                            print(
                                f"🤝 Бот {b_pid} {'принимает' if accept else 'отклоняет'} обмен"
                            )
                            game.respond_trade(b_pid, accept)
                    await broadcast_state(room_id)

                asyncio.create_task(bot_trade_response(bot_pid, offer))


async def handle_message(ws, message):
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return  # Игнорируем мусор

    action = data.get("action")

    try:
        if action == "create_room":
            room_id = generate_room_id()
            while room_id in rooms:
                room_id = generate_room_id()

            # Санитизация имени
            name = html.escape(str(data.get("name", "")).strip()[:20]) or "Хост"
            max_p = 4
            pts = safe_int(data.get("points_to_win"), 10, min_val=1, max_val=20)

            fog = bool(data.get("fog_of_war", False))
            fast_res = bool(data.get("fast_resources", False))
            fast_start = bool(data.get("fast_start", True))
            friendly_robber = bool(data.get("friendly_robber", True))
            poor_tax = bool(data.get("poor_tax", False))
            roles = bool(data.get("roles", False))
            events = bool(data.get("events", False))
            diplomacy = bool(data.get("diplomacy", False))

            game = Game(
                room_id,
                max_players=max_p,
                points_to_win=pts,
                fog_of_war=fog,
                fast_resources=fast_res,
                fast_start=fast_start,
                friendly_robber=friendly_robber,
                poor_tax=poor_tax,
                roles=roles,
                events=events,
                diplomacy=diplomacy,
            )

            player = game.add_player(name)
            player.connected = True

            rooms[room_id] = game
            connections[ws] = (room_id, player.player_id)
            room_connections.setdefault(room_id, {})[player.player_id] = ws

            await update_stats("games_created")  # Записываем статистику
            print(f"  ✅ Комната {room_id} создана")

            await ws.send(
                json.dumps(
                    {
                        "type": "room_created",
                        "room_id": room_id,
                        "player_id": player.player_id,
                        "reconnect_token": player.reconnect_token,
                    },
                    ensure_ascii=False,
                )
            )
            await broadcast_state(room_id)

        elif action == "join_room":
            room_id = str(data.get("room_id", "")).upper().strip()
            name = html.escape(str(data.get("name", "")).strip()[:20]) or "Игрок"
            lock = room_locks.setdefault(room_id, asyncio.Lock())
            async with lock:
                game = rooms.get(room_id)
                if not game:
                    await send_error(ws, f"Комната «{room_id}» не найдена")
                    return

                player = game.add_player(name)
                if not player:
                    await send_error(ws, "Комната полна или игра уже началась")
                    return

                player.connected = True
                connections[ws] = (room_id, player.player_id)
                room_connections.setdefault(room_id, {})[player.player_id] = ws
                cancel_room_cleanup(room_id)

            await ws.send(
                json.dumps(
                    {
                        "type": "joined",
                        "room_id": room_id,
                        "player_id": player.player_id,
                        "reconnect_token": player.reconnect_token,
                    },
                    ensure_ascii=False,
                )
            )
            await broadcast_state(room_id)

        elif action == "reconnect":
            room_id = str(data.get("room_id", "")).upper().strip()
            player_id = data.get("player_id")
            token = str(data.get("reconnect_token", ""))

            try:
                player_id = int(player_id)
            except (TypeError, ValueError):
                await send_error(ws, "Некорректный ID игрока")
                return

            lock = room_locks.setdefault(room_id, asyncio.Lock())

            # --- ИСПРАВЛЕНО: Теперь ВЕСЬ критический код внутри лока ---
            async with lock:
                game = rooms.get(room_id)
                if game is None or player_id < 0 or player_id >= len(game.players):
                    await send_error(ws, "Комната или игрок не найдены")
                    return

                player = game.players[player_id]

                if not token or not secrets.compare_digest(
                    token, player.reconnect_token
                ):
                    await send_error(ws, "Неверный токен")
                    return

                old_ws = room_connections.get(room_id, {}).get(player_id)
                if old_ws and old_ws != ws:
                    connections.pop(old_ws, None)
                    try:
                        await old_ws.close()
                    except:
                        pass

                player.connected = True
                connections[ws] = (room_id, player_id)
                room_connections.setdefault(room_id, {})[player_id] = ws
                cancel_room_cleanup(room_id)

            # Отправляем сообщения УЖЕ ВНЕ лока (так как это I/O операции, они не должны тормозить сервер)
            await ws.send(
                json.dumps(
                    {
                        "type": "reconnected",
                        "room_id": room_id,
                        "player_id": player_id,
                    },
                    ensure_ascii=False,
                )
            )
            await broadcast_state(room_id)

        elif action == "start_game":
            info = connections.get(ws)
            if not info:
                return
            room_id, pid = info
            game = rooms.get(room_id)

            if not game:
                return
            if pid != 0:
                await send_error(ws, "Только хост может начать игру")
                return

            result = game.start_game()
            if result.get("ok"):
                await broadcast_state(room_id)
            elif not result.get("already_started"):
                await send_error(ws, result.get("error", "Не удалось начать игру"))
            else:
                await broadcast_state(room_id)

        elif action == "add_bot":
            info = connections.get(ws)
            if not info:
                return
            room_id, pid = info

            lock = room_locks.setdefault(room_id, asyncio.Lock())
            async with lock:
                game = rooms.get(room_id)
                if not game:
                    return
                if pid != 0:
                    await send_error(ws, "Только хост может добавить бота")
                    return
                if game.phase != GamePhase.LOBBY:
                    await send_error(ws, "Ботов можно добавлять только в лобби")
                    return

                bot_names = ["🤖 C3PO", "🤖 R2D2", "🤖 T-800", "🤖 Валл-И"]
                b_name = (
                    bot_names[len(game.bot_pids)]
                    if len(game.bot_pids) < 4
                    else "🤖 Бот"
                )

                if not game.add_bot(b_name):
                    await send_error(ws, "Комната полна!")
                    return

            await broadcast_state(room_id)

        elif action == "game_action":
            info = connections.get(ws)
            if not info:
                return
            room_id, pid = info
            game = rooms.get(room_id)
            if not game:
                return

            game_action = data.get("game_action")
            params = data.get("params", {})

            # --- НОВОЕ: Защита от одновременных ходов ---
            lock = room_locks.setdefault(room_id, asyncio.Lock())
            async with lock:
                result = handle_game_action(game, pid, game_action, params)

            await ws.send(
                json.dumps(
                    {"type": "action_result", "result": result}, ensure_ascii=False
                )
            )
            await broadcast_state(room_id)

        elif action == "chat":
            info = connections.get(ws)
            if not info:
                return
            room_id, pid = info
            game = rooms.get(room_id)
            if not game:
                return

            msg = html.escape(str(data.get("msg", "")).strip()[:150])
            if msg:
                player = game.players[pid]
                game._add_log(f"💬 {player.name}: {msg}", pid)
                await broadcast_state(room_id)
    except Exception:
        traceback.print_exc()
        await send_error(ws, "Ошибка сервера")


def handle_game_action(game, pid, action, params):
    try:
        if action == "roll_dice":
            return game.roll_dice(pid)
        elif action == "setup_settlement":
            return game.setup_place_settlement(pid, int(params.get("vertex_id", -1)))
        elif action == "setup_road":
            return game.setup_place_road(pid, int(params.get("edge_id", -1)))
        elif action == "build_road":
            return game.build_road(pid, int(params.get("edge_id", -1)))
        elif action == "build_free_road":
            return game.build_free_road(pid, int(params.get("edge_id", -1)))
        elif action == "build_settlement":
            return game.build_settlement(pid, int(params.get("vertex_id", -1)))
        elif action == "build_city":
            return game.build_city(pid, int(params.get("vertex_id", -1)))
        elif action == "buy_dev_card":
            return game.buy_dev_card(pid)
        elif action == "play_dev_card":
            return game.play_dev_card(pid, params.get("card_type", ""), params)
        elif action == "move_pirate":
            return game.move_pirate(pid, int(params.get("hex_id", -1)))
        elif action == "choose_pirate_victim":
            return game.choose_pirate_victim(pid, int(params.get("victim_id", -1)))
        elif action == "discard":
            return game.discard_resources(pid, params.get("discards", {}))
        elif action == "trade_bank":
            return game.trade_with_bank(
                pid, params.get("give", ""), params.get("receive", "")
            )
        elif action == "end_turn":
            return game.end_turn(pid)
        elif action == "propose_trade":
            return game.propose_trade(
                pid, params.get("give", {}), params.get("want", {})
            )
        elif action == "respond_trade":
            return game.respond_trade(pid, params.get("accept", False))
        elif action == "cancel_trade":
            return game.cancel_trade(pid)
        return {"error": "Неизвестное действие"}
    except Exception:
        traceback.print_exc()
        return {"error": "Некорректные параметры"}


async def ws_handler(ws):
    try:
        async for message in ws:
            await handle_message(ws, message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        info = connections.pop(ws, None)
        if info:
            room_id, pid = info
            conns = room_connections.get(room_id, {})

            # --- ИСПРАВЛЕНО: Закрываем игрока только если это его АКТИВНЫЙ сокет ---
            if conns.get(pid) == ws:
                conns.pop(pid, None)

                game = rooms.get(room_id)
                if game and pid < len(game.players):
                    game.players[pid].connected = False

                    # Авто-сброс трейда при дисконнекте
                    if getattr(game, "active_trade_offer", None):
                        if game.active_trade_offer.from_player == pid:
                            game.active_trade_offer = None
                        else:
                            game.active_trade_offer.rejected_by.add(pid)
                            connected_others = {
                                p.player_id
                                for p in game.players
                                if p.connected
                                and p.player_id != game.active_trade_offer.from_player
                            }
                            if game.active_trade_offer.rejected_by >= connected_others:
                                game.active_trade_offer = None

                if conns:
                    await broadcast_state(room_id)
                else:
                    schedule_room_cleanup(room_id)


async def main():
    port = int(os.environ.get("PORT", 8765))

    print(f"[BOOT] Python: {sys.version}", flush=True)
    print(f"[BOOT] PORT: {port}", flush=True)

    async def process_request(connection, request):
        try:
            # Проверяем метод запроса — Render шлёт HEAD для health check
            method = getattr(request, "method", "GET")
            if method.upper() == "HEAD":
                return connection.respond(HTTPStatus.OK, "OK\n")

            path = getattr(request, "path", "?")
            upgrade = str(request.headers.get("Upgrade", ""))
            print(
                f"[HTTP] method={method} path={path!r} upgrade={upgrade!r}", flush=True
            )

            if upgrade.lower() != "websocket":
                return connection.respond(HTTPStatus.OK, "OK\n")

            return None
        except Exception:
            print("[process_request ERROR]", flush=True)
            traceback.print_exc()
            return connection.respond(HTTPStatus.INTERNAL_SERVER_ERROR, "ERROR\n")

    try:
        async with serve(
            ws_handler,
            "0.0.0.0",
            port,
            process_request=process_request,
            max_size=65536,
            ping_interval=20,
            ping_timeout=20,
        ) as server:
            print(f"[BOOT] listening on 0.0.0.0:{port}", flush=True)
            await server.serve_forever()
    except Exception:
        print("[BOOT ERROR]", flush=True)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())
