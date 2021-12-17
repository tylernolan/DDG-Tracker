from enum import Enum
from collections import defaultdict
from copy import deepcopy
import json
import os
import time
import logging
import requests
from subprocess import Popen
import traceback
DEBUG = False

r = requests.get("https://datadrivengaming.net/assets/json/cardIds.json").text
idMap = json.loads(r)
print(r)
class stateEnum(Enum):
	SHOP = 0
	COMBAT = 1
def getNameOrNone(card, cardDict):
	if card == None:
		return None
	return cardDict[card].DisplayName
def exportCardSnapNoDict(card):
	if card == None:
		return None
	return {"DisplayName":card.DisplayName, "Art":card.ArtContentID, "Attack":card.Attack,
			"Health":card.Health, "Golden":card.IsGolden}
def exportCardSnapshot(card, cardDict):
	if card == None:
		return None
	return exportCardSnapNoDict(cardDict[card])

class Boardstate():
	def __init__(self, turnCounter):
		self.boards = defaultdict(lambda: [None for x in range(7)])
		self.spells = defaultdict(lambda: None)
		self.heroes = defaultdict(None)
		self.treasures = defaultdict(lambda: [None for x in range(3)])
		self.turnCounter = turnCounter
		self.mutable = None
	def to_json(self, playerid=None):
		ret = defaultdict(dict)
		ret["turnCounter"] = self.turnCounter
		for player in self.heroes:
			ret[player]["start_board"] = [exportCardSnapNoDict(x) if x is not None else None for x in self.boards[player]]
			ret[player]["end_board"] = [exportCardSnapNoDict(x) if x is not None else None for x in self.mutable.boards[player]]
			ret[player]["treasures"] = [{"DisplayName":x.DisplayName, "Art":x.ArtContentID} if x is not None else None for x in self.treasures[player]]
			ret[player]["hero"] = exportCardSnapNoDict(self.heroes[player])
			ret[player]["spells"] = exportCardSnapNoDict(self.spells[player])
		if playerid != None:
			ret["playerId"] = playerid
		ret["winners"], ret["losers"] = self.getWinner()
		return ret
	def getJsonNames(self, playerId):
		ret = defaultdict(dict)
		opp = [x for x in self.heroes.keys() if x != playerId][0]
		HeroName = exportCardSnapNoDict(self.heroes[opp])["DisplayName"]
		ret[HeroName]["Units"] = [exportCardSnapNoDict(x)["DisplayName"]  if x is not None else None for x in self.boards[opp]]
		ret[HeroName]["Units"] += [x.DisplayName if x is not None else None for x in self.treasures[opp]]
		return ret
	def didPlayerWin(self, playerId):
		winners, losers = self.getWinner()
		if playerId in winners:
			return True
		return False
	def getWinner(self):
		winners = []
		losers = []
		for player in self.mutable.heroes.keys():
			if len([x for x in self.mutable.boards[player] if x is None]) < 7:
				winners.append(player)
			else:
				losers.append(player)
		return (winners, losers)
	def printBoards(self):
		str = ""
		for key in self.heroes.keys():
			try:
				str+=("Board: {}\n".format(["{} ({})".format(x.DisplayName, x.ID) for x in self.mutable.boards[key] if x != None]))
			except KeyError:
				str+= "Board: {}".format([None for x in range(7)])
		#print(str)
	def __str__(self):
		str = ""
		winners, losers = self.getWinner()
		if len(losers) == 2:
			str += "DRAW: {} ({}) vs. {} ({})".format(self.heroes[losers[0]].DisplayName, self.heroes[losers[0]].Health,
													  self.heroes[losers[1]].DisplayName, self.heroes[losers[1]].Health,)
		elif len(winners) == 2:
			str += "Weird DRAW: {} ({}) vs. {} ({}) {}".format(self.heroes[winners[0]].DisplayName, self.heroes[winners[0]].Health,
													  self.heroes[winners[1]].DisplayName, self.heroes[winners[1]].Health, self.heroes[winners[1]].Timestamp)
		else:
			str += "Winner: {} ({}) Loser: {} ({})".format(self.heroes[winners[0]].DisplayName, self.heroes[winners[0]].Health,
													   self.heroes[losers[0]].DisplayName, self.heroes[losers[0]].Health,)
		return str
	def old__str__(self):
		str = ""
		for key in self.heroes.keys():
			try:
				if self.spells[key] == None:
					raise KeyError
				str+=("Spell: {}\n".format(self.spells[key].DisplayName))
			except KeyError:
				str += "Spell: None\n"
			str+=("Hero: {}\n".format(self.heroes[key].DisplayName))
			try:
				str+=("Treasures: {}\n".format([x.DisplayName for x in self.treasures[key] if x != None]))
			except KeyError:
				str+= "Treasures: [None, None, None]\n"
			try:
				str+=("Board: {}\n".format([(x.DisplayName, x.ID, x.PlayerId) if x != None else None for x in self.boards[key]]))
			except KeyError:
				str+= "Board: {}\n".format([None for x in range(7)])
		if self.mutable != None:
			str += "ENDBOARD\n: {}".format(self.mutable.old__str__())
		return str

class Gamestate():
	def __init__(self):
		self.playerId = None
		self.board = [None for x in range(7)]
		self.hand = [None for x in range(4)]
		self.activeSpell = None
		self.hero = None
		self.currentHero = None
		self.treasures = [None for x in range(3)]
		self.shop = [None for x in range(10)]
		self.boughtUnits = []
		self.combatBoard = None
		self.combats = []
		self.cardDict = {}
		self.state = stateEnum.SHOP
		self.gold = 0
		self.turnCounter = 0
		self.initCombat = False
		self.gameCompleted=False
		self.eliminations = []
		self.shopRoll = 0
		self.boardSnaps = defaultdict(lambda: [])
		self.treasureSnaps = defaultdict(lambda: [])
		self.spellSnaps = defaultdict(lambda: None)
		self.hands = defaultdict(lambda: [])
		self.shops = defaultdict(lambda: [])
		self.firstActionSeen = None
	def ActionEnterBrawlPhase(self, action):
		self.turnCounter += 1
		self.combatBoard = Boardstate(self.turnCounter)
		self.state = stateEnum.COMBAT
		self.hands[self.turnCounter] = [exportCardSnapshot(x, self.cardDict) if x != None else None for x in self.hand]
		self.treasureSnaps[self.turnCounter] = [self.cardDict[x].DisplayName if x is not None else None for x in self.treasures]
		self.spellSnaps[self.turnCounter] = self.activeSpell
		self.boardSnaps[self.turnCounter] = [exportCardSnapshot(x, self.cardDict) if x != None else None for x in self.board]
		self.initCombat = True
	def ActionEnterShopPhase(self, action):
		self.state = stateEnum.SHOP
		self.ActionRoll(action)

	def ActionModifyGold(self, action):
		amount = int(action.Amount)
		if amount > 0:
			self.gold = amount
		else:
			self.gold -= amount
	def ActionAttack(self, action):
		#basically just a function for start of combat. Gets called by a bunch of other actions too.
		if self.combatBoard == None:
			return
		if self.initCombat == False:
			return
		self.initCombat = False
		self.combatBoard.boards[self.playerId] = [self.cardDict[x] if x != None else None for x in self.board]
		self.combatBoard.treasures[self.playerId] = [self.cardDict[x] if x != None else None for x in self.treasures]
		self.combatBoard.spells[self.playerId] = self.activeSpell
		self.combatBoard.heroes[self.playerId] = self.cardDict[self.currentHero]
		#(self.combatBoard.old__str__())
		self.combatBoard.mutable = deepcopy(self.combatBoard)

	def dumpCombatStart(self):
		if self.combatBoard is None or self.combatBoard.mutable is None:
			return
		f = open("lastCombat.json", 'w')
		f.write(json.dumps(self.combatBoard.to_json(playerid=self.playerId)))
		f.close()
	def ActionDeath(self, action):
		if self.initCombat:
			self.ActionAttack(action)
		target = self.cardDict[action.Target]
		if self.combatBoard is None:
			return
		boardSide = self.combatBoard.mutable.boards[target.PlayerId]
		for i in range(len(boardSide)):
			if boardSide[i] != None and boardSide[i].ID == target.ID:
				#print("Destroying: {} Slot: {}".format(boardSide[i].DisplayName, boardSide[i].Slot))
				boardSide[i] = None
				return
		#print(self.combatBoard.printBoards())
		if action.Target != self.hero and self.cardDict[action.Target].Zone == "Hero":
			#print("Eliminating {}".format(self.cardDict[action.Target].DisplayName))
			self.eliminations.append(action.Target)
		elif action.Target == self.hero:
			pass
			#print("Eliminated {}".format(self.cardDict[action.Target].DisplayName))
		else:
			print("not found {} {} {}".format(action.Timestamp, action.Target, self.cardDict[action.Target].DisplayName))
			print(self.combatBoard.old__str__())

	def ActionBrawlComplete(self, action):
		if self.initCombat:
			self.ActionAttack(action)
		if self.combatBoard != None:
			self.combats.append(self.combatBoard)
		#print(self.combatBoard)
	def ActionModifyXP(self, action):
		pass
	def ActionRoll(self, action):
		self.shopRoll += 1
		self.shops[self.shopRoll] = [self.turnCounter]
	def ActionDeathTrigger(self, action):
		pass
	def ActionSummonCharacter(self, action):
		pass
	def ActionModifyLevel(self, action):
		pass
	def ActionModifyNextLevelXP(self, action):
		pass
	def ActionSlayTrigger(self, action):
		pass
	def ActionPresentDiscover(self, action):
		pass
	def ActionEnterResultsPhase(self, action):
		self.gameCompleted = True
		self.placement = action.Placement
	def ActionEnterIntroPhase(self, action):
		pass
	def ActionPresentHeroDiscover(self, action):
		pass
	def ActionConnectionInfo(self, action):
		pass
	def ActionCastSpell(self, action):
		pass
	def ActionDealDamage(self, action):
		pass
	def ActionPlayFX(self, action):
		if self.initCombat:
			self.ActionAttack(action)
	def ActionUpdateTurnTimer(self, action):
		pass
	def ActionUpdateEmotes(self, action):
		pass
	def ActionAddPlayer(self, action):
		pass
	def ActionRemoveCard(self, action):
		pass
	def ActionEmote(self, action):
		pass
	def ActionMoveCard(self, action):
		try:
			oldLoc = self.cardDict[action.CardId].Zone
			oldSlot = int(self.cardDict[action.CardId].Slot)
			if oldLoc == "Shop":
				try:
					slotStart = min(self.shops[self.shopRoll][1:], key=lambda x: x[2])[2]
					self.shops[self.shopRoll][oldSlot - slotStart + 1][3] = True

				except:
					pass
				self.boughtUnits.append((self.shopRoll, self.cardDict[action.CardId].DisplayName,
										 self.cardDict[action.CardId].ArtContentID))
				#print(self.shops[self.shopRoll][oldSlot-slotStart+1])

			if oldLoc == "Hand" and self.hand[oldSlot] == action.CardId:
				self.hand[oldSlot] = None
			if oldLoc == "Character" and self.board[oldSlot] == action.CardId:
				self.board[oldSlot] = None
			self.cardDict[action.CardId].slot = action.TargetIndex  # ?
			index = int(action.TargetIndex)
			if action.TargetZone == "Hand":
				self.hand[index] = action.CardId
			elif action.TargetZone == "Character":
				self.board[index] = action.CardId
			elif action.TargetZone == "Spell":
				self.currentSpell = action.CardId
			elif action.TargetZone == "None":
				pass #? #self.cardDict[action.CardId] = None
			else:
				pass
		except KeyError:
			pass
	def ActionUpdateCard(self, action):
		self.cardDict[action.ID] = action
		if self.state == stateEnum.COMBAT and action.Zone == "Character" and self.combatBoard.mutable != None:
			self.combatBoard.mutable.boards[action.PlayerId][int(action.Slot)] = action

	def ActionCreateCard(self, action):
		self.cardDict[action.ID] = action
		if self.playerId == None:
			self.playerId = action.PlayerId
			self.currentHero = action.ID
			self.hero = action.ID
		if self.state == stateEnum.SHOP:
			if action.Zone == "Treasure" and int(action.Slot) >= 0:
				self.treasures[int(action.Slot)] = action.ID
			if action.Zone == "Character" and action.PlayerId == self.playerId:
				self.board[int(action.Slot)] = action.ID
			if action.Zone == "Hand":
				self.hand[int(action.Slot)] = action.ID
			if action.Zone == "Shop":
				self.shops[self.shopRoll].append([action.DisplayName, action.ArtContentID, int(action.Slot), False])
			if action.Zone == "Hero":
				self.currentHero = action.ID
		if self.state == stateEnum.COMBAT and self.initCombat:
			if action.Zone == "Character":
				self.combatBoard.boards[action.PlayerId][int(action.Slot)] = action
			elif action.Zone == "Hero":
				self.combatBoard.heroes[action.PlayerId] = action
			elif action.Zone == "Spell":
				self.combatBoard.spells[action.PlayerId] = action
			elif action.Zone == "Treasure":
				self.combatBoard.treasures[action.PlayerId][int(action.Slot)] = action
		elif self.state == stateEnum.COMBAT and action.Zone == "Character":
			self.combatBoard.mutable.boards[action.PlayerId][int(action.Slot)] = action

	def readGameAction(self, line):
		#try:
			action = GameAction(line)

			if self.firstActionSeen is None:
				self.firstActionSeen = action
			if int(self.firstActionSeen.Timestamp) > 20:
				return False  # if you're reconnecting to the game, just abandon trying to make a sensible game about it.

			self.__getattribute__(action.actionType)(action)

		#except AttributeError:
			#print("Unable to parse line: {}".format(line))
		#return True
	def exportGame(self, ddgUser, password, sentGames):
		if self.hero is None:
			return
		logging.debug("Starting game export")
		invariant = self.hero.replace("-", "")
		if invariant in sentGames:
			return None
		hero = json.dumps(exportCardSnapshot(self.hero, self.cardDict))
		combats = json.dumps([x.to_json() for x in self.combats])
		hands = json.dumps(self.hands)
		boughtUnits = json.dumps(self.boughtUnits)
		shops = json.dumps(self.shops)
		turnDead = self.turnCounter
		playerId = self.playerId
		if len(self.combats) == 0:
			return
		won = self.combats[-1].didPlayerWin(self.playerId)
		data={"username":ddgUser, "invariant":invariant, "password":password, "hero":hero, "combats":combats, "boughtUnits":boughtUnits, "shops":shops,
														   "turnDead":turnDead, "won":won, "playerId":playerId, "hands":hands, "placement":self.placement}
		logging.debug("data dumped")
		if DEBUG:
			r = requests.post("http://127.0.0.1:5000/sbb/recv", data=json.dumps(data))
		else:
			r = requests.post("https://datadrivengaming.net/sbb/recv", data=json.dumps(data))
		logging.debug("request posted")
		logging.debug("request: {}".format(r))
		print(r)
		return data
	def dumpCurrentState(self, prevSent = [None]):
		self.dumpCombatStart()
		ret = defaultdict(dict)
		try:
			ret["hero"] = self.cardDict[self.currentHero].DisplayName
		except KeyError:
			return
		ret["state"] = "SHOP"
		ret["shopSlots"] = [None for x in range(10)]
		for unit in self.shops[self.shopRoll][1:]:
			ret["shopSlots"][unit[2]] = unit[0]

		for unit in range(len(self.board)):
			ret["ownBoard"][unit] = getNameOrNone(self.board[unit], self.cardDict)
		for unit in range(len(self.hand)):
			ret["hand"][unit] = getNameOrNone(self.hand[unit], self.cardDict)
		for treasure in range(len(self.treasures)):
			ret["ownTreasures"] = [self.cardDict[x].DisplayName if x is not None else None for x in self.treasures]
		for combat in self.combats:
			ret["oppBoards"].update(combat.getJsonNames(self.playerId))
		if prevSent[0] == json.dumps(ret):
			return None
		else:
			prevSent[0] = json.dumps(ret)
		return ret


	def renderTerminal(self):
		for combat in self.combats:
			print(combat)
		#	print("")
		#for shop in self.shops:
		#	print(self.shops[shop])
		print("Hero: {}".format(self.cardDict[self.hero].DisplayName))
		print("Turn Over: {}".format(self.turnCounter))
		print("Bought: {}".format(self.boughtUnits))
		print("Hand: {}".format([self.cardDict[x].DisplayName if x in self.cardDict else None for x in self.hand]))
		print("Board: {}".format([self.cardDict[x].DisplayName if x in self.cardDict else None for x in self.board]))
		print("Eliminations: {}".format(self.eliminations))
		print(self.combats[-1].to_json())
		print("Won last fight: {}".format(self.combats[-1].didPlayerWin(self.playerId)))

class GameAction():
	def __init__(self, line):
		self.getData(line)

	def getData(self, line):
		line = line.split("\n")
		for i in range(len(line)):
			if line[i].startswith("UnityEngine") or line[i].startswith("(Filename:"):
				line = "".join(line[:i])
				break
		if type(line) == type([]):
			line = "".join(line)
		data = line.split("|")
		#print(data)
		self.bought = False
		self.actionType = data[0].split(":")[3].split(".")[-1].strip()
		for datum in data[1:]:
			stuff = datum.split(":") #actions involving a card have 2 colons
			if len(stuff) > 1:
				setattr(self, stuff[-2].strip(), stuff[-1].strip())

		try:
			self.DisplayName = idMap[self.CardTemplateId][1]
			self.ArtContentID = idMap[self.CardTemplateId][0]
		except AttributeError:
			pass
		except KeyError:
			self.DisplayName = "MISSINGNO"
			self.ArtContentID = "MISSINGNO"
			#print("Missing template ID: {}".format(self.CardTemplateId))

	def __str__(self):
		return("{} - {}".format(self.actionType, self.Timestamp))

def checkForUpdates():
	f = open("versionnum", 'r')
	versionNum = f.read()
	f.close()
	req = requests.get("https://datadrivengaming.net/sbb/trackerVersion")
	if(req.text == versionNum):
		return False
	return True

def parseFile(filename, username, password, mmr, sentGames):
	data = open(filename, encoding="utf-8").read()

	currentGS = None
	gamestates = []
	lines = []
	#cleanup step, ignore the useless lines. This is awful.
	#linebreaks in card effects linebreak in the log file too, this was the fastest workaround.
	data = data.split("\n")
	for line in data:
		if (line.startswith("Unloading") or line.startswith("Total:") or
				line.startswith("Got unused action") or line.startswith("CommsActionReceived") or
				line.startswith("UnityEngine") or line.startswith("SBB") or line.startswith("Filename:")
				or line.strip() == "" or line.startswith("!!!!") or line.startswith("GAME SERVER") or line.startswith(
					"UnloadTime") or line.startswith("SetEntity") or "STATECHANGE" in line or "[GameServer.Tick]" in line or "[MatchState.Tick]" in line
				or line.startswith("ActionUpdateCard")):
			pass
		else:
			lines.append(line)
	data = "\n".join(lines)
	data = data.split("Writing binary data to recorder for action")
	for line in data:
		line = line.strip()
		#print(line)
		if "Action:" in line:
			if currentGS != None:
				resp = currentGS.readGameAction(line)
				if resp == False:
					logging.debug("abandoning game")
					currentGS = None
		if "---- NEW GAME STARTED --------" in line:
			logging.debug("new game started")
			if currentGS != None:
				pass#

			currentGS = Gamestate()
			gamestates.append(currentGS)

		if currentGS is not None and currentGS.gameCompleted:
			exp = currentGS.exportGame(ddgUser=username, password=password, sentGames=sentGames)
			if exp != None:
				currentGS.dumpCurrentState()
				logging.debug("request sent, adding to sentGames {}".format(currentGS.playerId))
				sentGames.append(exp["invariant"])
				f = open("./sentGames.txt", 'w')
				f.write(json.dumps(sentGames))
				f.close()
			#currentGS.renderTerminal()
			currentGS = None
	if currentGS != None:
		logging.debug("Game in Progress")
		return currentGS

def debugFunc():
	username = "test"
	password = "password"
	mmr = 3000
	player = "./Player.log"
	sentGames = json.loads(open("./sentGames.txt", 'r').read())
	currentGame = parseFile(player, username, password, mmr, sentGames)
	sendExtensionData(currentGame, username, password)

def sendExtensionData(gs, username, password):
	data = gs.dumpCurrentState()
	req = {}
	req["username"] = username
	req["password"] = password
	req["gamestate"] = data
	if data != None:
		print(json.dumps(data))
		try:
			r = requests.post("https://datadrivengaming.net/sbb/observer/update", data=json.dumps(req))
			print(r)
		except requests.exceptions.ConnectionError:
			return
	#f = open("testdata.json", 'w')
	#f.write(json.dumps(data))
	#f.close()

def mainFunc():
	if checkForUpdates() and not DEBUG:
		Popen('./Updater.exe')
	else:
		logging.basicConfig(filename='./logfile1.log', level=logging.DEBUG)
		try:
			config = open("./config.txt", 'r').readlines()
		except FileNotFoundError:
			username = input("Enter your DDG username: ")
			password = input("Enter your DDG password: ")
			mmr = input("Enter your SBB Rating: ")
			stream = input("(leave blank if you're not streaming) Enter your twitch username: ")
			f = open("./config.txt", 'w')
			f.write("ddgUsername={}\nddgPassword={}\nmmr={}\nstream={}".format(username, password, mmr, stream))
			f.close()
			config = open("./config.txt", 'r').readlines()
		username = None
		password = None
		stream = ""
		mmr = 0
		appdata = os.getenv('APPDATA')
		filename = "\\".join(appdata.split("\\")[:-1]) + "\LocalLow\Good Luck Games\Storybook Brawl"
		for line in config:
			if line.startswith("ddgUsername"):
				username = line.split("=")[1].strip()
			if line.startswith("ddgPassword"):
				password = line.split("=")[1].strip()
			if line.startswith("mmr"):
				mmr = line.split("=")[1].strip()
			if line.startswith("stream"):
				stream = line.split("=")[1].strip()
			if line.startswith("appdataoverride"):
				filename = line.split("=")[1].strip()

		print(username)
		playerprev = filename + "\\player-prev.log"
		player = filename + "\\player.log"
		print(player, playerprev)
		if stream == "":
			streaming = False
		else:
			streaming = True

		while True:
			try:
				sentGames = json.loads(open("./sentGames.txt", 'r').read())
			except FileNotFoundError:
				f = open("./sentGames.txt", 'w')
				f.write("[]")
				f.close()
				sentGames = []
			if not streaming:
				currentGame = parseFile(player, username, password, mmr, sentGames)
				parseFile(playerprev, username, password, mmr, sentGames)
				time.sleep(30)
			else:
				currentGame = parseFile(player, username, password, mmr, sentGames)

				if currentGame == None:
					time.sleep(2)
				else:
					sendExtensionData(currentGame, username, password)
					time.sleep(2)
if __name__ == "__main__":
	try:
		if not DEBUG:
			mainFunc()
		else:
			print("call trynet dumb, he pushed this with the debug flag LUL")
			mainFunc()
	except:
		traceback.print_exc()
		input()
