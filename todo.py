import time
import datetime
import re
import json
import csv
import os
import copy
import sys

# Make it so list below is auto-generated from command dict.
"""
disp [o]rder [lh | hl] - Sorts between high and low urgency.
disp [g]roupCategories [y | n] - Enables or disables grouping by category.
disp [n]umItems [num=10] - Sets the number of items to display.
- When category grouped, the categories with the highest total urgency show up first.

set defaultTime [time='7d'] - Sets the default allotted time for a task.
set critTaskMult [mult=1.0] - Sets the urgency multiplier for critical tasks.
set disp [command] - Sets default display appearance.
set catIsTask [y | n] - Sets whether categories are themselves tasks that need to be completed.
set logHistory [y | n] - Sets whether to log history.
set urgencyFunc beforeDue percent [func(percent_time_remaining)) -> float] -
- will be rescaled so that it passes through (1,1))
- Keeps track of initial assignment date
set urgencyFunc beforeDue absolute [func(days_time_remaining) -> float] [multiplier=1.0] # Doesn't care about due date
- will be rescaled so that it passes through (1, multiplier))
- Only cares about remaining time, not assignment date
set urgencyFunc pastDue percent [func(percent_past_due) -> float] (will be rescaled so that it passes through (1,1))
set urgencyFunc pastDue absolute [func(days_past_due) -> float] [multiplier=1.0]


a [taskname] [c]at]egory]=[itemname | itemid]=none [due]date]="defaultTime" [crit]ical]=[y | n]=n [p]arent]=[itemname | itemid] - Adds a task under a category.
d [itemname | itemid] [reason] - Deletes an item and all subitems.
c [itemname | itemid] [date=now] - Completes an item and all subitems.
e [itemname | itemid] [name | due | crit] - Edits the name, due date, or criticality of an item.
exp [] export history in various different formats to file

"""
class ToDo():
    def __init__(self) -> None:
        self.commandDict = {
            ("display", "disp",): {
                "func": self.setDisplay,
                "args": {
                    ("order", "ord", "o"): ["lh", "hl", None],
                    ("category", "cat", "c"): ["n", "y", None],
                    ("numItems", "num", "n"): [int, None],
                    ("gridwidth", "gw"): [int, None],
                    ("gridheight", "gh"): [int, None],
                    # None in args means that the argument is optional
                },
                "defargs": {
                    "order": None,
                    "category": None,
                    "numItems": None,
                    "gridWidth": None,
                    "gridHeight": None,
                    # None in defargs means that no arg will be passed if none is specified
                },
                "help": "Sets the display appearance.",
            },
            ("set",): { # Single-length alias lists MUST have a comma otherwise they're interpreted as individual characters!
                ("defaultTime", "dt"): {
                    "func": self.setDefaultTime,
                    "args": {("time"): [str]},
                    "defargs": {"time": "7d"},
                    "help": "Sets the default allotted time for a task.",
                },
                ("critTaskMult", "ctm"): {
                    "func": self.setCritTaskMult,
                    "args": {("mult"): [float]},
                    "defargs": {"mult": 1.0},
                    "help": "Sets the urgency multiplier for critical tasks.",
                },
                ("disp", "d", "display"): { 
                    "func": self.setStartupCommand,
                    "args": {("command"): [str]},
                    "defargs": {"command": None},
                    "help": "Sets default display appearance.",
                },
                ("catIsTask"): { # This is only for the CREATION of categories, the property can be edited
                    "func": self.setCatIsTask,
                    "args": {("catistask"): ["n", "y"]},
                    "defargs": {"catistask": "n"},
                    "help": "Sets whether categories are themselves tasks that need to be completed.",
                },
                ("catPersistence"): {
                    "func": self.setCatPersistence,
                    "args": {("catpersistence"): ["n", "y"]},
                    "defargs": {"catpersistence": "n"},
                    "help": "Sets whether categories persist after all subtasks are completed.",
                },
                ("logHistory"): {
                    "func": self.setLogHistory,
                    "args": {("loghist"): ["n", "y"]},
                    "defargs": {"loghist": "n"},
                    "help": "Sets whether to log history.",
                },
                ("urgencyFunc"): {
                    ("beforeDue"): {
                        "func": self.setUrgFuncBeforeDue,
                        "args": {
                            ("type"): ["percent", "absolute"],
                            ("function"): [str],
                            ("multiplier"): [float, None],
                        },
                        "defargs": {
                            "type": "percent",
                            "function": "x",
                            "multiplier": 1.0,
                        },
                        "help": "Sets the urgency function for tasks before their due date.",
                    },
                    ("pastDue"): {
                        "func": self.setUrgFuncPastDue,
                        "args": {
                            ("type"): ["percent", "absolute"],
                            ("function"): [str],
                            ("multiplier"): [float, None],
                        },
                        "defargs": {
                            "type": "percent",
                            "function": "x",
                            "multiplier": 1.0,
                        },
                        "help": "Sets the urgency function for tasks after their due date.",
                    },
                },
            },
            ("additem", "add", "a",): {
                "func": self.addItem,
                "args": {
                    ("name", "n"): [str],
                    ("due", "du"): [str, None],
                    ("category", "ca"): [str, None],
                    ("critical", "cr"): [str, None],
                },
                "defargs": {
                    "name": None,
                    "due": None,
                    "category": None,
                    "critical": None,
                },
                "help": "Adds a task under a category.",
            },
            ("delete", "del", "d",): {
                "func": self.deleteItem,
                "args": {
                    ("item", "i"): [str],
                    ("reason", "re"): [str],
                },
                "defargs": {
                    "item": None,
                    "reason": None,
                },
                "help": "Deletes an item and all subitems.",
            },
            ("complete", "comp", "c",): {
                "func": self.completeItem,
                "args": {
                    ("item", "i"): [str],
                    ("date", "da"): [str, None],
                },
                "defargs": {
                    "item": None,
                    "date": None,
                },
                "help": "Completes an item and all subitems.",
            },
            ("edit", "e",): {
                "func": self.editItem,
                "args": {
                    ("item", "i"): [str],
                    ("attribute", "at"): ["name", "due", "crit", "n", "du", "cr"],
                    ("value", "va"): [str],
                },
                "defargs": {
                    "item": None,
                    "attribute": None,
                    "value": None,
                },
                "help": "Edits the name, due date, or criticality of an item.",
            },
            ("export", "exp",): {
                "func": self.exportHistory,
                "args": {
                    ("type"): ["current", "history"],
                    ("format"): ["csv", "json", "txt"],
                    ("file"): [str],
                },
                "defargs": {
                    "type": "current",
                    "format": "csv",
                    "file": "MinTodoExport",
                },
                "help": "Exports history in various different formats to file.",
            },
        }

        self.taskDict = {}
        
        self.settings = { # This dict should NOT be modified at runtime! Instead, the names are saved into the class as attributes, 
        "displayGridWidth": 80, # and the attributes are retrieved when saved.
        "displayGridHeight": 40,
        "displayOrder": "lh",
        "displayGroupCategories": False,
        "displayMaxNumItems": 10,
        "itemDefaultAllottedTime": 24*60*60*7, # 7 days
        "itemCriticalMultiplier": 1.0,
        "startupCommands": [],
        "logHistory": False,
        "categoryPersistence": False
        }
        for k, v in self.settings.items():
            setattr(self, k, v)

    def getInput(self):
        command = input("> ")
        args = command.split(" ")
        for i, arg in enumerate(args):
            if arg == "":
                args.remove(arg)
            else:
                args[i] = arg.lower()
        return args
            
    def executeInput(self):
        args = self.getInput()
        args = [a.lower() for a in args]
        if len(args) == 0:
            return
        
        cdict = self.commandDict
        for i, arg in enumerate(args):
            foundfunc, cdict = self.getNextArglist(arg, cdict)
            if foundfunc:
                status = self.executeFunction(cdict, " ".join(args[i+1:]).split(","))
                if status:
                    self.refresh_screen()
                return
            elif cdict is None:
                print("Invalid command.")
                return
            elif i == len(args) - 1:
                print("Invalid command.")
                return
            
    def executeFunction(self, funcInfo, userargs):
        userargs = [a.strip() for a in userargs]
        # print('execfunc ', userargs) # debug
        # userargs = " ".join(userargs).split(",")
        func = funcInfo["func"]
        args = funcInfo["args"]
        defargs = funcInfo["defargs"]
        help = funcInfo["help"]
        kwmode = False
        kwarg = None
        finalArgs = defargs.copy()
        argopts = []
        i = 0
        for arg in userargs:
            # print(f'arg: {arg}, i: {i}') # debug
            # print(f'kwarg {kwarg} arg {arg}') # debug
            if arg == "help":
                print(help)
                return
            if kwarg and kwmode:
                if arg in argopts:
                    try:
                        finalArgs[kwarg] = arg
                    except KeyError:
                        print(f'Invalid argument: {arg} is not a valid argument name.\nValid names: {arg_name_list}\nNote that any keyword syntax("argname" "val") must occur after any normal syntax ("val" "val"..)')
                        return
                else:
                    if type(argopts[0]) == type:
                        try:
                            arg = argopts[0](arg)
                            finalArgs[kwarg] = arg
                        except ValueError: # evaluating argument of kw, wrong type
                            print(f'Invalid argument: {arg} is not a {argopts[0].__name__}.')
                            return
                    else: # evaluating argument of kw, must be one of the options, isn't
                        print(f'Invalid argument: {arg} is not a valid argument name.\nValid names: {argopts}')
                        return
                kwarg = None
                i += 1
            else:
                for arg_name_list in args.keys():
                    if arg in arg_name_list:
                        argopts = args[arg_name_list]
                        kwarg = arg_name_list[0]
                        kwmode = True
                        break
                if not kwmode:
                    finalArgs[list(defargs.keys())[i]] = arg
                    i += 1
        # print(finalArgs) # debug

        for i, arg in enumerate(defargs.keys()):
            if None not in list(args.values())[i]:
                if finalArgs[arg] is None:
                    print(f'Missing argument: {arg} is required.')
                    return
        
        status = func(**finalArgs)
        return status
        
    def getNextArglist(self, key, cdict):
        valid_args = []
        for args in cdict.keys():
            valid_args.extend(args)
        if key in valid_args:
            for alias_list in cdict.keys():
                if key in alias_list:
                    key = alias_list
                    break
            cdict = cdict[key]
            if "func" in cdict.keys():
                foundfunc, next_cdict = True, cdict
            else:
                foundfunc, next_cdict = False, cdict
        else:
            foundfunc, next_cdict = False, None
            
        return foundfunc, next_cdict
    
    def generateLine(self, widths, info=None):
        if info is None:
            line = "+"
            for w in widths:
                line += "─" * w + "+"
        else:
            line = "|"
            for i, w in enumerate(widths):
                line += info[i].center(w) + "|"
        return line

    def printGrid(self):
        # below line sorts dict by urgency
        rev = True if self.displayOrder == "lh" else False
        self.taskDict = dict(sorted(self.taskDict.items(), key=lambda item: self.calculateUrgency(item[0]), reverse=rev))
        names = [self.taskDict[i]["name"] for i in self.taskDict.keys()]
        dues_float = [self.taskDict[i]["due"] for i in self.taskDict.keys()]
        dues = [datetime.datetime.utcfromtimestamp(d).strftime("%b %d") for d in dues_float]
        assigneds = [datetime.datetime.utcfromtimestamp(self.taskDict[i]["assigned"]).strftime("%b %d, %Y") for i in self.taskDict.keys()]
        criticals = ["Y" if self.taskDict[i]["critical"] else "N" for i in self.taskDict.keys()]
        urgencies = [f'{self.calculateUrgency(i):02.0f}' for i in self.taskDict.keys()]
        remainings = [d - time.time() for d in dues_float]
        ids = [str(i) for i in self.taskDict.keys()]
        hour = 60*60
        day = 24*hour
        week = 7*day
        month = 30*day
        for i, r in enumerate(remainings):
            weeks, remainder = divmod(r, week)
            days, remainder = divmod(remainder, day)
            hours, remainder = divmod(remainder, hour)
            remainings[i] = f'{str(int(weeks)) + "w " if weeks != 0 else ""}{str(int(days)) + "d " if days != 0 else ""}{str(int(hours)) + "h " if hours != 0 else ""}'

        headers = ["Task", "ID", "Time Left", "Critical", "Urgency"]
        columns = [names, ids, remainings, criticals, urgencies]
        # print(columns) # debug
        padding = 2 
        if len(self.taskDict) > 0:
            widths = [max(len(sorted(c, key=lambda z: len(z))[-1]), len(headers[i]))+padding for i, c in enumerate(columns)]
        else:
            widths = [len(h)+padding for h in headers]
        spaceper = self.displayGridWidth - (len(headers) + 1)
        spaceper = spaceper // len(headers) # Width won't be the same as specified width.
        print(self.generateLine(widths))
        print(self.generateLine(widths, headers)) # Column names: Task, TimeRemaining, Crit, Urg. Extras: Due, Assigned, Children
        print(self.generateLine(widths))

        item = 0
        while item <= (len(self.taskDict) - 1):
            try:
                info = [c[item] for c in columns]
            except IndexError:
                info = ["" for i in range(len(headers))]
            print(self.generateLine(widths, info))
            item += 1
        print(self.generateLine(widths))
        sys.stdout.flush()
    
    def saveTasksAndSettings(self, filename="tasks_and_settings"):
        tasks_and_settings = {
            "tasks": self.taskDict,
            "settings": {k: getattr(self, k) for k in self.settings.keys()},
        }

        with open(f'{filename}.json', 'w') as jsonfile:
            json.dump(tasks_and_settings, jsonfile)

    def loadTasksAndSettings(self, filename="tasks_and_settings.json"):
        try:
            with open(filename, 'r') as jsonfile:
                tasks_and_settings = json.load(jsonfile)
            self.taskDict = tasks_and_settings["tasks"]
            self.taskDict = {int(k): v for k, v in self.taskDict.items()}
            self.settings = tasks_and_settings["settings"]
        except FileNotFoundError:
            print("No tasks and settings file found. Creating new one.")
            self.saveTasksAndSettings()
        for k, v in self.settings.items():
                setattr(self, k, v)

    def findItem(self, item):
        try:
            item = int(item)
            try:
                _ = self.taskDict[item]
                return item
            except KeyError:
                return None
        except ValueError:
            for id, task in self.taskDict.items():
                if task["name"].lower() == item:
                    return id
            return None

    def parseDate(self, input_string):
        input_string = input_string.strip() # leading/trailing spaces cause issues

        now = datetime.datetime.now()

        # Handle relative time formats
        match = re.match(r"(\d+)\s?([dwm])", input_string)
        if match:
            amount, unit = int(match.group(1)), match.group(2)
            if unit == 'd':
                return int((now + datetime.timedelta(days=amount)).timestamp())
            elif unit == 'w':
                return int((now + datetime.timedelta(weeks=amount)).timestamp())
            elif unit == 'm':
                return int((now + datetime.timedelta(days=30 * amount)).timestamp())

        # Handle absolute time formats
            
        numerical_fmts = ["%m/%d", "%m %d", "%m/%d/%Y", "%m %d %Y"]
        month_name_fmts = ["%b %d", "%b%d", "%d %b", "%d%b", "%B %d", "%d %B"]
        year_fmts = [" %Y"] # Adding %y might be nice but increases ambiguity and probably increases false readings
        time_fmts = ["%I%p", "%I %p", "%H"] # %H might cause similar issues
        all_fmts = []
        for mnf in month_name_fmts:
            all_fmts.append(mnf) # Adds each month-name format
            for yf in year_fmts:
                all_fmts.append(mnf + yf) # Adds year format to the end of each month-name format
        all_fmts.extend(numerical_fmts)
        
        af = all_fmts.copy() # Important that this is NOT a reference or copied inside the time fmt loop - will get entries with multiple different time formats
        for tf in time_fmts:
            for f in af:
                all_fmts.append(tf + " " + f) # Adds time format to beginning and end of each format
                all_fmts.append(f + " " + tf)
        # print(f'len: {len(all_fmts)}') # debug

        try:
            for fmt in all_fmts: # Add %Y to end of each (with space). Add %I%p to start and end of each (with space, with and without middle space). 
                try:
                    # print(f'fmt: {fmt}') # debug
                    date = datetime.datetime.strptime(input_string, fmt)
                    print(f'hit: {fmt}!') # debug
                    yr = (now.year if abs(date.month - now.month) < 2 else now.year + 1) if not ("%Y" in fmt) else date.year
                    date = date.replace(year=yr, minute=59)
                    if fmt.endswith("%I%p"):
                        date = date.replace(hour=date.hour - 1)  # Adjust for 11:59 PM
                    return int(date.timestamp())
                except ValueError:
                    continue
        except ValueError:
            pass

        # raise ValueError("Invalid date format")
        return None

    def calculateUrgency(self, id):
        assigned = self.taskDict[id]["assigned"]
        due = self.taskDict[id]["due"]
        allotted = due - assigned
        critical = self.itemCriticalMultiplier if self.taskDict[id]["critical"] else 1.0
        remaining = due - time.time()
        urgency = (1 - (remaining / allotted)) * critical
        return urgency*100

    def create_csv_from_tasks(self, tasks, filename):
        tasks = copy.deepcopy(tasks)
        for t in tasks.keys():
            tasks[t]["urgency_at_completion"] = self.calculateUrgency(t)
        if tasks and isinstance(tasks, dict):
            with open(filename, 'w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=tasks[next(iter(tasks))].keys())
                writer.writeheader()
                for task in tasks.values():
                    writer.writerow(task)

    def append_task_to_csv(self, task, filename, completion_text, date):
        task = task.copy()
        task['completion_text'] = completion_text  # Add the completion text to the task dictionary
        task['completion_date'] = date
        task['urgency_at_completion'] = self.calculateUrgency(self.findItem(task['name']))
        file_exists = os.path.isfile(filename)
        try:
            with open(filename, 'a', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=task.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(task)
            return True
        except PermissionError:
            return False

    def clear_screen(self):
        if os.name == 'nt':  # for Windows
            _ = os.system('cls')
        else:  # for macOS and Linux
            _ = os.system('clear')

    def refresh_screen(self):
        self.clear_screen()
        self.printGrid()

    def findItemWrapper(self, item):
        item = self.findItem(item)
        if item is None:
            print("Item not found: ID or name is invalid. Try again.")
            return None
        return item

### Below: User-accessible commands that might print stuff. Should return True if they are successful.

    def setDisplay(self, order, category, numItems, gridWidth, gridHeight):
        if order is not None:
            self.displayOrder = order
        if category is not None:
            self.displayGroupCategories = category
        if numItems is not None:
            self.displayMaxNumItems = numItems
        if gridWidth is not None:
            self.displayGridWidth = gridWidth
        if gridHeight is not None:
            self.displayGridHeight = gridHeight
        return True
        
    def setDefaultTime(self, time):
        time = self.parseDate(time)
        if time is None: # default time should never be on order of years
            print("Invalid date format, refer to help command.")
            return
        elif time > 60*60*24*365:
            print("Default time cannot be greater than one year.")
            return
        self.itemDefaultAllottedTime = time
        return True

    def setCritTaskMult(self, mult):
        try:
            mult = float(mult)
            self.itemCriticalMultiplier = mult
            return True
        except ValueError:
            print("Invalid critical task multiplier: must be a float.")
            return

    def setStartupCommand(self, command):
        pass

    def setCatIsTask(self, catistask):
        if catistask == "y" or catistask == "n":
            self.categoryIsTask = True if catistask == "y" else False
            return True
        else:
            print("Invalid category is task value: must be y or n.")
            return

    def setCatPersistence(self, catpersistence):
        if catpersistence == "y" or catpersistence == "n":
            self.categoryPersistence = True if catpersistence == "y" else False
            return True
        else:
            print("Invalid category persistence value: must be y or n.")
            return

    def setLogHistory(self, loghist):
        pass

    def setUrgFuncBeforeDue(self, type, function, multiplier):
        pass

    def setUrgFuncPastDue(self, type, function, multiplier):
        pass

    def addItem(self, name, category, due, critical):
        if category is not None:
            catid = self.findItemWrapper(category)
            if catid is None:
                print("Invalid category: category not found.")
                return
        else:
            catid = 0

        if due is None:
            due = time.time() + self.itemDefaultAllottedTime
        else:
            due = self.parseDate(due)
            if due is None:
                print("Invalid date format, refer to help command.")
                return
        if critical is None:
            critical = False
        else:
            if critical == "y" or critical == "n":
                critical = True if critical == "y" else False
            else:
                print("Invalid criticality value: must be y or n.")
                return
        try:
            _ = float(name)
            print("Invalid name: must be a string with non-numeric characters.")
            return
        except:
            pass
        self.taskDict[len(self.taskDict)] = {
            "name": name,
            "due": due,
            "assigned": time.time(),
            "critical": critical,
            "isTask": True,
            "parent": catid,
        }
        return True

    def deleteItem(self, item, reason, date=time.time()):
        id = self.findItemWrapper(item)
        if id is None:
            return
        status = self.append_task_to_csv(self.taskDict[id], "MinTodoHistory.csv", reason, date)
        if not status:
            print("Unable to write to history file because it is open in another program. Please close the file and try again.")
        else:
            del self.taskDict[id]
            return True


        # deal with subitems

    def completeItem(self, item, date):
        if date is None:
            compdate = time.time()
        else:
            compdate = self.parseDate(date)
            if compdate is None:
                print("Invalid date format, refer to help command.")
                return
        return self.deleteItem(item, "Completed", compdate)
        # Add points according to completed urgency (lower is better)?

    def editItem(self, item, attribute, value):
        id = self.findItemWrapper(item)
        if id is None:
            return
        if attribute == "name" or attribute == "n":
            try:
                _ = float(value)
                print("Invalid name: must be a string with non-numeric characters.")
                return
            except ValueError:
                self.taskDict[id]["name"] = value
                return True
        elif attribute == "due" or attribute == "du":
            date = self.parseDate(value)
            if date is None:
                print("Invalid date format, refer to help command.")
                return
            self.taskDict[id]["due"] = date
            return True
        elif attribute == "crit" or attribute == "cr":
            if value == "y" or value == "n":
                self.taskDict[id]["critical"] = True if value == "y" else False
                return True
            else:
                print("Invalid criticality value: must be y or n.")
                return
        
    def exportHistory(self, type, format, file):
        if type == "current" and format == "csv":
            self.create_csv_from_tasks(self.taskDict, file + ".csv")
            return True
        else:
            print("Not yet supported")
            return

###

td = ToDo()
td.loadTasksAndSettings()
td.refresh_screen()
while True:
    # print(td.taskDict) # debug
    td.executeInput()
    td.saveTasksAndSettings()



