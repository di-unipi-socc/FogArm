import os
import requests
import configparser

from timeloop import Timeloop
from datetime import timedelta

from signal import *

from utils import *


tl = Timeloop()

BASE_FOLDER = os.path.dirname(os.path.realpath(__file__))+"/"

CONFIG_FILE = BASE_FOLDER+"config.ini"

config = configparser.ConfigParser()
config.read(CONFIG_FILE)

PID_FILE = BASE_FOLDER+".tmp/.fogWatcher.pid"

INFRA_WAITING_TIME = int(config["WATCHER"]["infra_waiting_time"])
INFRA_PATH = BASE_FOLDER+"infrastructure/infra.pl"
INFRA_HASH = ""

APP_WAITING_TIME = int(config["WATCHER"]["app_waiting_time"])
APP_HASH = {}

DEPLOYMENT_WAITING_TIME = int(config["WATCHER"]["deployment_waiting_time"])

SERVER_WAITING_TIME = 0.1

SERVER = ''

#PERIODIC_CHECK = int(config["WATCHER"]["periodic_check"])

def app_hash(path):
    try:
        new_hash_compose = hash_file(path+"/docker-compose.yml")
    except:
        return None
    try:
        new_hash_reqs = hash_file(path+"/requirements.yml")
    except:
        return new_hash_compose
    return new_hash_compose+new_hash_reqs

def trigger(application):
    try:
        if not execute_cmd("fogarmx exec "+application):
            print("-> Error while executing fogarmx exec "+application)
            return False
        return True
    except Exception as e:
        print("-> Exception "+e+" while executing fogarmx exec "+application)
        return False

def trigger_all():
    for app,path in get_apps().items():
        new_app_hash = app_hash(path)
        if new_app_hash is not None:
            APP_HASH[app] = new_app_hash
            trigger(app)

def rm(application):
    if not execute_cmd("fogarmx rm "+application):
        print("-> Error while executing fogarmx rm "+application)
        return False
    return True

@tl.job(interval=timedelta(seconds=INFRA_WAITING_TIME))
def check_infra():
    print("-> FogWatcher: checking infrastructure")
    global INFRA_HASH
    new_hash = hash_file(INFRA_PATH)
    if new_hash != INFRA_HASH:
        INFRA_HASH = new_hash
        print("-> Infra changed, triggering all apps")
        trigger_all()

@tl.job(interval=timedelta(seconds=APP_WAITING_TIME))
def check_reqs():
    print("-> FogWatcher: checking apps")
    global APP_HASH

    for app,path in get_apps().items():
        print("-> FogWatcher: checking app "+app)
        new_hash = app_hash(path)
        if new_hash is not None and (app not in APP_HASH or new_hash != APP_HASH[app]):
            APP_HASH[app] = new_hash
            print("-> App "+app+" changed, triggering")
            trigger(app)

@tl.job(interval=timedelta(seconds=DEPLOYMENT_WAITING_TIME))
def check_deployments():
    print("-> FogWatcher: checking deployments")
    for app in get_apps():
        if not verify_placement(app):
            print("-> Deployment of "+app+" not matched, triggering")
            remove_deployment(app)
            trigger(app)

@tl.job(interval=timedelta(seconds=SERVER_WAITING_TIME))
def check_server():
    url = SERVER+"/applications"
    try:
        data = requests.get(url).json()
        if data != {} and "application" in data and data["application"] != "" and "operation" in data and data["operation"] != "":
            print("-> New Server request: "+data["application"]+" "+data["operation"])
            if data["operation"] == "rm":
                rm(data["application"])
            elif data["operation"] == "exec":
                trigger(data["application"])
            elif data["operation"] == "update":
                print("-> Updating "+data["application"])
                path = get_apps()[data["application"]]
                if "compose" in data:
                    try:
                        with open(path+"/docker-compose.yml", "w+") as stream:
                            stream.write(data["compose"])
                    except FileNotFoundError as exc:
                        print(exc)

                if "requirements" in data:
                    try:
                        with open(path+"/requirements.yml", "w+") as stream:
                            stream.write(data["requirements"])
                    except FileNotFoundError as exc:
                        print(exc)
                print("-> Updating "+data["application"]+" done")

                print("-> Triggering "+data["application"])
                trigger(data["application"])
    except:
        pass
        #print("-> Error while checking server")

# @tl.job(interval=timedelta(seconds=PERIODIC_CHECK))
# def periodic_check():
#     print("-> Periodic Check, triggering all apps")
#     trigger_all()

def is_running():
   return os.path.exists(PID_FILE)

def run():
    if is_running():
        return False
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    print("-> FogWatcher started")
    check_infra()
    check_reqs()
    check_deployments()
    tl.start(block=True)
    os.remove(PID_FILE)
    return True

def clean(*args):
    try:
        os.remove(PID_FILE)
        tl.stop()
        exit(0)
    except:
        exit(1)

for sig in (SIGABRT, SIGILL, SIGINT, SIGSEGV, SIGTERM):
    signal.signal(sig, clean)


if __name__ == "__main__":
    run()
        