from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from pusher import Pusher
from django.http import JsonResponse
from decouple import config
from django.contrib.auth.models import User
from .models import *
from rest_framework.decorators import api_view
import json
from django.utils import timezone
from datetime import datetime, timedelta

# instantiate pusher
pusher = Pusher(app_id=config('PUSHER_APP_ID'), key=config('PUSHER_KEY'), secret=config('PUSHER_SECRET'), cluster=config('PUSHER_CLUSTER'))

SHOP_ROOM_ID=1
NAME_CHANGE_ROOM_ID=467
HOLLOWAY_SHRINE_ROOM_ID=22

PENALTY_COOLDOWN_VIOLATION=5
PENALTY_NOT_FOUND=5
PENALTY_CANNOT_MOVE_THAT_WAY=5
PENALTY_TOO_HEAVY=5
PENALTY_UPHILL = 5

PENALTY_BLASPHEMY = 10

MIN_COOLDOWN = 1
MAX_COOLDOWN = 600

def check_cooldown_error(player):
    """
    Return cooldown error if cooldown is bad, None if it's valid
    """
    if player.cooldown > timezone.now():
        t_delta = (player.cooldown - timezone.now())
        cooldown_seconds = min(MAX_COOLDOWN, t_delta.seconds + t_delta.microseconds / 1000000 + PENALTY_COOLDOWN_VIOLATION)
        player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
        player.save()
        return JsonResponse({"cooldown": cooldown_seconds, 'errors':[f"Cooldown Violation: +{PENALTY_COOLDOWN_VIOLATION}s CD"]}, safe=True, status=400)
    return None

def api_response(player, cooldown_seconds, errors=None, messages=None):
    if errors is None:
        errors = []
    if messages is None:
        messages = []
    room = player.room()
    if player.is_pm:
        response = JsonResponse({'room_id':room.id,
                                 'title':room.title,
                                 'description':room.description,
                                 'coordinates':room.coordinates,
                                 'elevation':room.elevation,
                                 'terrain':room.terrain,
                                 'players':room.playerNames(player.id, True),
                                 'items':room.itemNames(),
                                 'exits':room.exits(),
                                 'cooldown': cooldown_seconds,
                                 'errors': errors,
                                 'messages':messages}, safe=True)
    else:
        response = JsonResponse({'room_id':room.id,
                                 'title': room.title,
                                 'description':room.description,
                                 'coordinates':room.coordinates,
                                 'elevation':room.elevation,
                                 'terrain':room.terrain,
                                 'players':room.playerNames(player.id, True),
                                 'items':room.itemNames(),
                                 'exits':room.exits(),
                                 'cooldown': cooldown_seconds,
                                 'errors': errors,
                                 'messages':messages}, safe=True)
    return response


def player_api_response(player, cooldown_seconds, errors=None, messages=None):
    if errors is None:
        errors = []
    if messages is None:
        messages = []
    response = JsonResponse({'name':player.name,
                             'cooldown': cooldown_seconds,
                             'encumbrance': player.encumbrance,
                             'strength': player.strength,
                             'speed': player.speed,
                             'gold': player.gold,
                             'inventory': player.inventory(),
                             'status': [],
                             'errors': errors,
                             'messages': messages}, safe=True)
    return response

def item_examine_api_response(item, cooldown_seconds, errors=None, messages=None):
    if errors is None:
        errors = []
    if messages is None:
        messages = []
    response = JsonResponse({'name':item.name,
                             'description':item.description,
                             'weight':item.weight,
                             'itemtype':item.itemtype,
                             'level':item.level,
                             'exp':item.exp,
                             'attributes':item.attributes,
                             'cooldown': cooldown_seconds,
                             'errors': errors,
                             'messages': messages}, safe=True)
    return response

def player_examine_api_response(player, cooldown_seconds, errors=None, messages=None):
    if errors is None:
        errors = []
    if messages is None:
        messages = []
    response = JsonResponse({'name':player.name,
                             'description':player.name + player.description,
                             'cooldown': cooldown_seconds,
                             'errors': errors,
                             'messages': messages}, safe=True)
    return response


def get_cooldown(player, cooldown_scale):
    speed_adjustment = player.speed - 10
    time_factor = float(config('TIME_SCALE'))
    if player.is_pm:
        time_factor = min(time_factor, 5)
    return max(MIN_COOLDOWN, cooldown_scale * time_factor - speed_adjustment)



@csrf_exempt
@api_view(["GET"])
def initialize(request):
    player = request.user.player

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    cooldown_seconds = get_cooldown(player, 0.0)
    player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
    player.save()

    return api_response(player, cooldown_seconds)


@api_view(["POST"])
def move(request):
    player = request.user.player
    # import pdb; pdb.set_trace()
    data = json.loads(request.body)

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    dirs={"n": "north", "s": "south", "e": "east", "w": "west"}
    reverse_dirs = {"n": "south", "s": "north", "e": "west", "w": "east"}
    direction = data['direction']
    room = player.room()
    nextRoomID = None
    cooldown_seconds = get_cooldown(player, 1.0)
    errors = []
    messages = []
    if direction == "n":
        nextRoomID = room.n_to
    elif direction == "s":
        nextRoomID = room.s_to
    elif direction == "e":
        nextRoomID = room.e_to
    elif direction == "w":
        nextRoomID = room.w_to
    if nextRoomID is not None and nextRoomID >= 0:
        nextRoom = Room.objects.get(id=nextRoomID)
        player.currentRoom=nextRoomID
        messages.append(f"You have walked {dirs[direction]}.")
        elevation_change = player.room().elevation - room.elevation
        if elevation_change > 0:
            messages.append(f"Uphill Penalty: {PENALTY_UPHILL}s CD")
            cooldown_seconds += PENALTY_UPHILL
        if player.strength <= player.encumbrance:
            messages.append(f"Heavily Encumbered: +100% CD")
            cooldown_seconds *= 2
        if 'next_room_id' in data:
            if data['next_room_id'].isdigit() and int(data['next_room_id']) == nextRoomID:
                messages.append(f"Wise Explorer: -50% CD")
                cooldown_seconds /= 2
            else:
                messages.append(f"Foolish Explorer: +50% CD")
                cooldown_seconds *= 1.5
    else:
        cooldown_seconds += PENALTY_CANNOT_MOVE_THAT_WAY
        errors.append(f"You cannot move that way: +{PENALTY_CANNOT_MOVE_THAT_WAY}s CD")
    player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
    player.save()
    return api_response(player, cooldown_seconds, errors=errors, messages=messages)




@api_view(["POST"])
def take(request):
    player = request.user.player
    data = json.loads(request.body)

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    alias = data['name']
    room = player.room()
    item = room.findItemByAlias(alias)
    cooldown_seconds = get_cooldown(player, 0.5)
    errors = []
    messages = []
    if item is None:
        cooldown_seconds += PENALTY_NOT_FOUND
        errors.append(f"Item not found: +{PENALTY_NOT_FOUND}s CD")
    elif player.strength * 2 <= player.encumbrance + item.weight:
        cooldown_seconds += PENALTY_TOO_HEAVY
        errors.append(f"Item too heavy: +{PENALTY_TOO_HEAVY}s CD")
    else:
        messages.append(f"You have picked up {item.name}")
        player.addItem(item)
    player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
    player.save()
    return api_response(player, cooldown_seconds, errors=errors, messages=messages)


@api_view(["POST"])
def drop(request):
    player = request.user.player
    data = json.loads(request.body)

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    alias = data['name']
    room = player.room()
    item = player.findItemByAlias(alias)
    cooldown_seconds = get_cooldown(player, 0.5)
    errors = []
    messages = []
    if item is None:
        cooldown_seconds += PENALTY_NOT_FOUND
        errors.append(f"Item not found: +{PENALTY_NOT_FOUND}s CD")
    else:
        messages.append(f"You have dropped {item.name}")
        room.addItem(item)
    player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
    player.save()
    return api_response(player, cooldown_seconds, errors=errors, messages=messages)


@api_view(["POST"])
def examine(request):
    player = request.user.player
    data = json.loads(request.body)

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    alias = data['name']
    room = player.room()
    # import pdb; pdb.set_trace()
    item = room.findItemByAlias(alias)
    if item is None:
        item = player.findItemByAlias(alias)
    players = room.findPlayerByName(alias)
    cooldown_seconds = get_cooldown(player, 0.5)
    errors = []
    messages = []
    if item is not None:
        # Examine item
        player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
        player.save()
        return item_examine_api_response(item, cooldown_seconds, errors=errors, messages=messages)
    if len(players) > 0:
        # Examine player
        player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
        player.save()
        return player_examine_api_response(players[0], cooldown_seconds, errors=errors, messages=messages)
    cooldown_seconds += PENALTY_NOT_FOUND
    errors.append(f"Item not found: +{PENALTY_NOT_FOUND}s CD")
    player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
    player.save()
    return api_response(player, cooldown_seconds, errors=errors, messages=messages)




@api_view(["POST"])
def status(request):
    player = request.user.player

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    cooldown_seconds = get_cooldown(player, 0)

    return player_api_response(player, cooldown_seconds)


@api_view(["POST"])
def sell(request):
    player = request.user.player
    data = json.loads(request.body)

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    cooldown_seconds = get_cooldown(player, 0.2)

    errors = []
    messages = []

    if player.currentRoom != SHOP_ROOM_ID:
        cooldown_seconds += PENALTY_NOT_FOUND
        errors.append("Shop not found: +{PENALTY_NOT_FOUND}")
    else:
        item = player.findItemByAlias(data["name"])
        if item is None:
            cooldown_seconds += PENALTY_NOT_FOUND
            errors.append(f"Item not found: +{PENALTY_NOT_FOUND}s CD")
        elif "confirm" not in data or data["confirm"].lower() != "yes":
            messages.append(f"I'll give you {item.value} gold for that {item.name}.")
            messages.append(f"(include 'confirm':'yes' to sell {item.name})")
        else:
            messages.append(f"Thanks, I'll take that {item.name}.")
            messages.append(f"You have received {item.value} gold.")
            if item.itemtype == "TREASURE":
                item.levelUpAndRespawn()
            else:
                item.unsetItem()
            player.gold += item.value

    player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
    player.save()
    return api_response(player, cooldown_seconds, errors=errors, messages=messages)


@api_view(["POST"])
def wear(request):
    player = request.user.player
    data = json.loads(request.body)

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    alias = data['name']
    item = player.findItemByAlias(alias)
    cooldown_seconds = get_cooldown(player, 0.5)
    errors = []
    messages = []
    if item is None:
        cooldown_seconds += PENALTY_NOT_FOUND
        errors.append(f"Item not found: +{PENALTY_NOT_FOUND}s CD")
    else:
        if player.wearItem(item):
            messages.append(f"You wear {item.name}")
        else:
            messages.append(f"You cannot wear {item.name}")
    player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
    player.save()
    return api_response(player, cooldown_seconds, errors=errors, messages=messages)


@api_view(["POST"])
def remove(request):
    player = request.user.player
    data = json.loads(request.body)

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    # alias = data['name']
    # item = player.findItemByAlias(alias)
    # cooldown_seconds = get_cooldown(player, 0.5)
    # errors = []
    # messages = []
    # if item is None:
    #     cooldown_seconds += PENALTY_NOT_FOUND
    #     errors.append(f"Item not found: +{PENALTY_NOT_FOUND}s CD")
    # else:
    #     if player.wearItem(item):
    #         messages.append(f"You wear {item.name}")
    #     else:
    #         messages.append(f"You cannot wear {item.name}")
    # player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
    # player.save()
    return api_response(player, cooldown_seconds, errors=errors, messages=messages)



@api_view(["POST"])
def change_name(request):
    player = request.user.player
    data = json.loads(request.body)

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    new_name = data['name']
    cooldown_seconds = get_cooldown(player, 2.0)
    errors = []
    messages = []
    if player.currentRoom != NAME_CHANGE_ROOM_ID:
        cooldown_seconds += 5 * PENALTY_NOT_FOUND
        player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
        player.save()
        errors.append("Name changer not found: +{5 * PENALTY_NOT_FOUND}")
    else:
        player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
        player.name = new_name
        player.save()
        messages.append(f"You have changed your name to {new_name}.")
    return api_response(player, cooldown_seconds, errors=errors, messages=messages)




@api_view(["POST"])
def pray(request):
    player = request.user.player

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    cooldown_seconds = get_cooldown(player, 5.0)
    errors = []
    messages = []
    if player.currentRoom != HOLLOWAY_SHRINE_ROOM_ID:
        cooldown_seconds += 5 * PENALTY_NOT_FOUND
        player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
        player.save()
        errors.append("Shrine not found: +{5 * PENALTY_NOT_FOUND}")
    else:
        player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
        player.can_fly = True
        player.save()
        messages.append(f"You notice your body starts to hover above the ground.")
    return api_response(player, cooldown_seconds, errors=errors, messages=messages)





@api_view(["POST"])
def fly(request):
    player = request.user.player
    data = json.loads(request.body)

    cooldown_error = check_cooldown_error(player)
    if cooldown_error is not None:
        return cooldown_error

    dirs={"n": "north", "s": "south", "e": "east", "w": "west"}
    reverse_dirs = {"n": "south", "s": "north", "e": "west", "w": "east"}
    direction = data['direction']
    room = player.room()
    nextRoomID = None
    cooldown_seconds = get_cooldown(player, 1.0)
    errors = []
    messages = []
    if direction == "n":
        nextRoomID = room.n_to
    elif direction == "s":
        nextRoomID = room.s_to
    elif direction == "e":
        nextRoomID = room.e_to
    elif direction == "w":
        nextRoomID = room.w_to
    print("HERE")
    if not player.can_fly:
        cooldown_seconds += PENALTY_BLASPHEMY
        errors.append(f"You cannot fly: +{PENALTY_BLASPHEMY}s CD")
    elif nextRoomID is not None and nextRoomID >= 0:
        nextRoom = Room.objects.get(id=nextRoomID)
        player.currentRoom=nextRoomID
        messages.append(f"You have flown {dirs[direction]}.")
        elevation_change = player.room().elevation - room.elevation
        if player.strength <= player.encumbrance:
            messages.append(f"Flying while Heavily Encumbered: +200% CD")
            cooldown_seconds *= 3
        elif elevation_change < 0:
            messages.append(f"Downhill Flight Bonus: Instant CD")
            cooldown_seconds = 1.0
        else:
            messages.append(f"Flight Bonus: -10% CD")
            cooldown_seconds *= 0.9
        if 'next_room_id' in data:
            if data['next_room_id'].isdigit() and int(data['next_room_id']) == nextRoomID:
                messages.append(f"Wise Explorer: -50% CD")
                cooldown_seconds /= 2
            else:
                messages.append(f"Foolish Explorer: +50% CD")
                cooldown_seconds *= 1.5
    else:
        cooldown_seconds += PENALTY_CANNOT_MOVE_THAT_WAY
        errors.append(f"You cannot move that way: +{PENALTY_CANNOT_MOVE_THAT_WAY}s CD")
    player.cooldown = timezone.now() + timedelta(0,cooldown_seconds)
    player.save()
    return api_response(player, cooldown_seconds, errors=errors, messages=messages)

