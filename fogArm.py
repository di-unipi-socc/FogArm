#!/usr/bin/python3

import os
import sys
import time
import yaml
import signal
import argparse
import requests
import tempfile
import subprocess
from pyswip import Prolog

from utils import *

import fogWatcher

SERVER = ''

VERSION = "0.1.0"
AUTHORS = "GBisi"
LICENSE = ""
REPOSITORY = "https://github.com/di-unipi-socc/FogArm"

BASE_FOLDER = os.path.dirname(os.path.realpath(__file__))+"/"

STATS = {}
STATS_FILE = BASE_FOLDER+"stats.json"

def info():
    print("-> FogArm")
    print("-> Version:",VERSION)
    print("-> Authors:",AUTHORS)
    print("-> License:",LICENSE)
    print("-> Repository:",REPOSITORY)
    #print("-> Website:",WEBSITE)
    print("-> FogArm is a tool to deploy applications on a fog-enabled infrastructure")

class Service:
    def __init__(self, name, sw=[], hw=0, iot=[]):
        self._name = name
        self._sw = sw
        self._hw = hw
        self._iot = iot

    def as_fact(self):
        return f"service({self._name}, {self._sw}, {self._hw}, {self._iot}).".replace("'","")

    def get_name(self):
        return self._name

class S2S:
    def __init__(self, s1, s2, bw=0, lat="inf"):
        self._s1 = s1
        self._s2 = s2
        self._bw = bw
        self._lat = lat

    def as_fact(self):
        return f"s2s({self._s1}, {self._s2}, {self._lat}, {self._bw})."

class Application:
    def __init__(self, name):
        self._name = name
        self._services_name = []
        self._services = []
        self._s2s = []

    def add_service(self, s):
        self._services_name.append(s.get_name())
        self._services.append(s)

    def add_s2s(self, s2s):
        self._s2s.append(s2s)

    def as_kb(self):
        kb = f":-dynamic deployment/3.\n\
:-dynamic application/2.\n\
:-dynamic service/4.\n\
:-dynamic s2s/4.\n\
:-dynamic link/4.\n\
:-dynamic node/4.\n\n\
application({self._name}, {self._services_name}).\n\n".replace("'","")
        for s in self._services:
            kb += s.as_fact()+"\n"
        kb += "\n"
        for s2s in self._s2s:
            kb += s2s.as_fact()+"\n"
        kb += "\n"

        return kb

    def get_name(self):
        return self._name

def parse_requirements(path):
    global STATS
    try:
        with open(path+"/docker-compose.yml", "r") as stream:
            try:
                compose = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
    except FileNotFoundError as exc:
        print("-> docker-compose Not Found in this Folder")
        STATS["error"] = "docker-compose Not Found in this Folder"
        return None

    try:
        with open(path+"/requirements.yml", "r") as stream:
            try:
                requirements = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
    except FileNotFoundError as exc:
        print("-> Application Requirements Not Found in this Folder")
        requirements = None

    app = os.path.basename(os.path.normpath(path))
    if requirements is not None and "application" in requirements:
        app = requirements["application"]
    app = Application(app)

    if "services" in compose:
        for s in compose["services"]:
            sw = []
            hw = 0
            iot = []
            if requirements is not None:
                v = requirements["services"]
                if v is not None and s in v:
                    if v[s] is not None:
                        reqs = v[s]
                        if "software" in reqs:
                            sw = reqs["software"]
                        if "hardware" in reqs:
                            hw = reqs["hardware"]
                        if "iot" in reqs:
                            iot = reqs["iot"]
                        if "links" in reqs:
                            s2s = reqs["links"]
                            for e,l in s2s.items():
                                lat = "inf"
                                bw = 0
                                if "latency" in l:
                                    lat = l["latency"]
                                if "bandwidth" in l:
                                    bw = l["bandwidth"]
                                app.add_s2s(S2S(s,e,lat=lat,bw=bw))
            app.add_service(Service(s,sw,hw,iot))

    return app

def extract_placement(s):
    s = s[3:-1].split(",")
    parsed = []
    for e in s:
        e = e.replace(" ", "")
        if e.startswith("b'"):
            e = e[2:]
        e = e.replace("'","")
        parsed.append(e)
    if len(parsed) == 2:
        return (parsed[0], parsed[1])
    elif len(parsed) == 3:
        return (parsed[0], parsed[1], parsed[2])


def process_app(path):
    global STATS
    app = parse_requirements(path)

    if app is not None:
        try:
            with tempfile.NamedTemporaryFile() as tmp:
                with open(tmp.name, 'w') as f:
                    f.write(app.as_kb())
                    print(f"-> Application requirements [{app.get_name()}]\n")
                    print(app.as_kb())

                prolog = Prolog()
                prolog.consult(tmp.name)
                prolog.consult(BASE_FOLDER+"fogArmX.pl")
                prolog.consult(BASE_FOLDER+"infrastructure/infra.pl")

                start = time.time() 

                ans = my_query("fogArmX(ToAdd, ToRemove, ToMigrate)", prolog)

                end = time.time()

                my_query("unload_file('"+tmp.name+"')", prolog)
                my_query("unload_file('"+BASE_FOLDER+"fogArmX.pl')", prolog)
                my_query("unload_file('"+BASE_FOLDER+"infrastructure/infra.pl')", prolog)
                my_query("retractall(deployment(_,_,_))", prolog)
                my_query("retractall(application(_,_))", prolog)
                my_query("retractall(service(_,_,_,_))", prolog)
                my_query("retractall(s2s(_,_,_,_))", prolog)
                my_query("retractall(link(_,_,_,_))", prolog)
                my_query("retractall(node(_,_,_,_))", prolog)

            if ans is None:
                print("-> ERROR: No Placement Found")
                rollback(app.get_name())
                STATS["error"] = "No Placement Found"
                return#
                sys.exit(1)

            STATS["fogbrain"] = end-start

            placement = {"application": app.get_name()}

            try:
                STATS["current_placement"] = get_current_placement(app.get_name())
            except Exception as e:
                print("-> ERROR: Unable to get current placement due to {}".format(e))

            for k,l in ans.items():
                placement[k] = []
                for v in l:
                    placement[k].append(extract_placement(v))
                
            return placement
        except Exception as e:
            print("-> ERROR *:",e)
            STATS["error"] = "Process App Exception"
            return None

    return None

def delete_application(application, complete=False):
    global STATS
    try:
        os.remove(BASE_FOLDER+".tmp/.placements/."+application)
        print("-> Removed Placement")
    except:
        print("-> Placement not found while trying to remove it")

    if complete:
        delete_app(application)

        cmd = f"docker stack rm {application}"
        try:
            print("-> Executing", cmd)
            if subprocess.run(cmd.split()).returncode != 0:
                print("-> CRITICAL ERROR: REMOVE FAILED")
            else:
                print("-> Remove completed")
                publish_update(application, "rm")
        except:
            STATS["error"] = "CRITICAL ERROR: REMOVE FAILED"
            print("-> CRITICAL ERROR: REMOVE FAILED")

def rollback(application, complete=False):
    global STATS
    STATS["rollback"] = True
    print("-> AN ERROR OCCURED: Starting Rollback")
    publish_update(application, "rollback")
    delete_application(application, complete)
    print("-> ROLLBACK COMPLETED")


def execute_command(cmd, application, complete_rollback=False):
    global STATS
    print("-> Executing",cmd)
    try:
        if not execute_cmd(cmd):
            rollback(application, complete_rollback)
        else:
            return True
    except Exception as e:
        print("-> ERROR X:",e)
        STATS["error"] = "Error while executing command "+cmd
        rollback(application, complete_rollback)

    return False

def execute(cmd, application, complete_rollback=False):
    global STATS
    if execute_command(cmd, application, complete_rollback):
        return True
    else:
        STATS["error"] = "Error while executing command "+cmd
        return False#
        sys.exit(1)

def actuate_placement(placement, path, complete_rollback=False):
    global STATS
    if placement is not None:

        global_start = time.time()

        STATS["Placement"] = placement

        print("-> Placement:",placement)
        if len(placement["ToAdd"]) != 0:

            STATS["ToAdd"] = len(placement["ToAdd"])
            start = time.time()
            if not execute(f"docker stack deploy --compose-file {path}/docker-compose.yml {placement['application']}", placement['application'], complete_rollback):
                return None
            print("\n-> Initial Placement: ", get_current_placement()) #TODO: filter for only that application (startswith)
            print()
            
            for s,n in placement["ToAdd"]:
                if not execute(f"docker service update --constraint-add node.hostname=={n} {placement['application']}_{s}", placement['application'], complete_rollback):
                    return None
            end = time.time()
            STATS["avg-to_add"] = (end-start) / STATS["ToAdd"]

        for s,oldN,newN in placement["ToMigrate"]:

            STATS["ToMigrate"] = len(placement["ToMigrate"])
            start = time.time()
            if not execute(f"docker service update --constraint-rm node.hostname=={oldN} {placement['application']}_{s}", placement['application'], complete_rollback):
                return None
            if not execute(f"docker service update --constraint-add node.hostname=={newN} {placement['application']}_{s}", placement['application'], complete_rollback):
                return None
            end = time.time()
            STATS["avg-to_migrate"] = (end-start) / STATS["ToMigrate"]
            

        for s,_ in placement["ToRemove"]:

            STATS["ToRemove"] = len(placement["ToRemove"])
            start = time.time()
            if not execute(f"docker service rm {placement['application']}_{s}", placement['application'], complete_rollback):
                return None
            end = time.time()
            STATS["avg-to_remove"] = (end-start) / STATS["ToRemove"]
        print("-> Placement Executed")

        global_end = time.time()
        STATS["actuate"] = global_end-global_start

        try:
            publish_update(placement['application'], "exec")
        except Exception as e:
            print("-> ERROR: Unable to publish update {} due to {}".format(placement, e))

    return placement

def manage(path, complete_rollback=False, cmd=None):
    #return actuate_placement(process_app(path), path, complete_rollback)
    global STATS
    STATS = {}

    if cmd is not None:
        STATS["cmd"] = cmd

    STATS["app"] = path

    STATS["timestamp"] = time.time()
    ans = actuate_placement(process_app(path), path, complete_rollback)
    STATS["total_time"] = time.time() - STATS["timestamp"]

    if ans is None:
        try:
            print("-> ERROR during actuate")
            rollback(STATS["Placement"]["application"], complete_rollback)
            STATS["error"] = "Error during actuate"
        except:
            print("-> ERROR during rollback")
            STATS["error"] = "Error during rollback"

    STATS_LIST = []
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            try:
                STATS_LIST = json.load(f)
            except:
                print("-> ERROR: Unable to load stats file")

    STATS_LIST.append(STATS)

    with open(STATS_FILE, "w+") as f:
        json.dump(STATS_LIST, f)

    return ans

def main(args):
    if args.cmd is None:
        args.cmd = "exec"
        args.application = "all"
    
    if args.cmd == "add":
        print("-> Adding Application")
        path = store_app(args.path)
        if path is not None and manage(path, complete_rollback=True, cmd="add "+args.path) is not None:
            print("-> Application Added")
            return#
            sys.exit(0)
    elif args.cmd == "rm":
        apps = get_apps()
        application = args.application
        if application is None:
            try:
                with open(os.path.normpath(os.path.abspath("."))+"/requirements.yml", "r") as stream:
                    try:
                        requirements = yaml.safe_load(stream)
                        application = requirements["application"]
                    except yaml.YAMLError as exc:
                        print(exc)
            except:
                application = os.path.basename(os.path.normpath(os.path.abspath(".")))
        if application == "all":
            for a in apps:
                print("-> Removing Application", a)
                delete_application(a, complete=True)
                print("")
            print("-> All Applications Removed")
            return#
            sys.exit(0)
        elif application in apps:
            delete_application(application, complete=True)
            return#
            sys.exit(0)
        else:
            print(f"-> The application {application} does not exist")
    elif args.cmd == "exec":
        application = args.application
        apps = get_apps()
        if application == "all":
            error = False
            print("-> Executing all applications")
            for app,path in apps.items():
                print(f"-> Executing {app}")
                if manage(path, cmd="exec all") is None:
                    print(f"-> Error while executing {app}")
                    error = True
            if not error:
                print("-> All applications executed")
                return#
                sys.exit(0)
        else:
            if application in apps:
                if manage(apps[application], cmd="exec "+application) is not None:
                    return#
                    sys.exit(0)
    elif args.cmd == "watcher":
        op = args.operation
        if op == "start":
            if fogWatcher.is_running():
                print("-> FogWatcher already running")
            else:
                print("-> FogWatcher started")
                execute_cmd("python3 "+BASE_FOLDER+"fogWatcher.py", background=True)
        elif op == "stop":
            if fogWatcher.is_running():
                with open(fogWatcher.PID_FILE, "r") as f:
                    pid = f.read()
                os.kill(int(pid), signal.SIGTERM)
                print("-> FogWatcher stopped")
            else:
                print("-> FogWatcher not running")
        elif op == "restart":
            if fogWatcher.is_running():
                with open(fogWatcher.PID_FILE, "r") as f:
                    pid = f.read()
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except:
                    pass
                print("-> FogWatcher stopped")
            execute_cmd("python3 "+BASE_FOLDER+"fogWatcher.py", background=True)
            print("-> FogWatcher started")
        elif op == "status":
            if fogWatcher.is_running():
                print("-> FogWatcher running")
            else:
                print("-> FogWatcher not running")   

    elif args.cmd == "status":
        print("-> Current placement:", get_current_placement()) 
        print("")
        print("-> Available applications:")
        apps = get_apps()
        for app,path in apps.items():
            print(f"   - {app}")
            print(f"      - Path: {path}")
            try:
                matched = verify_placement(app)
                if matched:
                    matched = "MATCHED"
                else:
                    matched = "NOT MATCHED"
                print(f"      - Desired Placement: {parse_deployment(BASE_FOLDER+'.tmp/.placements/.'+app)} ({matched})")
                if matched == "NOT MATCHED":
                    print(f"      - Current Placement: {get_current_placement(app)}")
            except:
                print(f"      - Desired Placement: N/A")
        if len(apps) == 0:
            print("   No applications deployed")
        print("")
        if fogWatcher.is_running():
            print("-> FogWatcher: Running")
        else:
            print("-> FogWatcher: Not running") 

    elif args.cmd == "info":
        info()

    elif args.cmd == "help":
        info()
        print("-> Usage:")
        print("   - fogArmX.py [options]")
        print("")
        print("   - add <path>")
        print("       - Add an application to the system")
        print("   - rm <application>")
        print("       - Remove an application from the system")
        print("   - exec <application>")
        print("       - Execute an application")
        print("   - watcher <operation>")
        print("       - Start/Stop/Status the fogWatcher")
        print("   - status")
        print("       - Show the current placement")
        print("   - info")
        print("       - Show information about FogArmX")
        print("   - help")
        print("       - Show this help")
        print("")
        print("   - <application> can be:")
        print("       - all")
        print("       - <application>")
        print("")
        print("   - <operation> can be:")
        print("       - start")
        print("       - stop")
        print("       - restart")
        print("       - status")
        print("")

    else:
        print("-> Unknown command")

    return#  
    sys.exit(1)

def publish_update(application, cmd):
    if application is not None:
        print("-> Publishing update on '"+SERVER+"'")
        report = {"application": application, "timestamp": time.time()*1000, "placement": {"current":get_current_placement()}}

        if cmd == "add" or cmd == "exec" or cmd == "rollback":
            path = get_apps()[application]
            report["online"] = True

            try:
                with open(path+"/docker-compose.yml", "r") as stream:
                    try:
                        report["compose"] = stream.read()
                    except yaml.YAMLError as exc:
                        print(exc)
            except FileNotFoundError as exc:
                print(exc)
                return

            try:
                with open(path+"/requirements.yml", "r") as stream:
                    try:
                        report["requirements"] = stream.read()
                    except yaml.YAMLError as exc:
                        print(exc)
                        return
            except FileNotFoundError as exc:
                pass 
            
            report["placement"]["application_current"] = get_current_placement(application)
            if cmd == "rollback":
                report["placement"]["desired"] = []
                report["placement"]["matched"] = False
            else:
                report["placement"]["desired"] = parse_deployment(BASE_FOLDER+'.tmp/.placements/.'+application)
                report["placement"]["matched"] = verify_placement(application)
        elif cmd == "rm":
            report["online"] = False

        url = SERVER+"/applications"
        try:
            requests.post(url, json=report)
        except:
            print("-> Error while publishing update")

        time.sleep(1)


PID_FILE = BASE_FOLDER+".tmp/.fogArm.pid"

def clean(*args):
    try:
        os.remove(PID_FILE)
        os._exit(0)
    except:
        os._exit(1)

def is_running():
    return os.path.exists(PID_FILE)

def now_running():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

for sig in (signal.SIGABRT, signal.SIGILL, signal.SIGINT, signal.SIGSEGV, signal.SIGTERM):
    signal.signal(sig, clean)


if __name__ == "__main__":

    start = time.time()
    delta = 900

    while is_running() and time.time() - start < delta:
        time.sleep(1)

    if is_running():
        print("-> FogWatcher is already running")
        os._exit(2)

    now_running()

    parser = argparse.ArgumentParser(prog='FogArmX')
    
    sp = parser.add_subparsers(dest='cmd')
    sp_add = sp.add_parser('add', help='Add an application')
    sp_rm = sp.add_parser('rm', help='Remove an application')
    sp_exec = sp.add_parser('exec', help='Execute a reasoning step')
    sp_watcher = sp.add_parser('watcher', help='Manage FogWatcher')
    sp_info = sp.add_parser('info', help='Show information about the application')
    sp_status = sp.add_parser('status', help='Show current placement')
    sp_help = sp.add_parser('help', help='Show help')

    sp_add.add_argument('path',
                       help=f"Add an application folder",
                       metavar="PATH",
                       default = ".", nargs='?')

    sp_rm.add_argument('application',
                       help=f"Remove an application",
                       metavar="APPLICATION",
                       nargs='?')

    sp_exec.add_argument('application',
                       help=f"Execute a reasoning step",
                       metavar="APPLICATION",
                       default = "all", nargs='?')

    sp_watcher.add_argument('operation',
                       help=f"Start/Stop/Restart/Status FogWatcher",
                       metavar="OPERATION",
                       choices=['start', 'stop', "status", "restart"])

    

    args = parser.parse_args()

    main(args)

    clean()
    
    
    







