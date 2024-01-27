import os
import signal
import requests
import subprocess
import time
import json

_BASE_FOLDER = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))+"/"
_INFRA_PATH = _BASE_FOLDER+"infrastructure/infra.pl"

_SERVER = ''

EXECUTE_CMD_TIMEOUT = 3600

def get_apps():
    try:   
        with open(_BASE_FOLDER+'/.tmp/.APPS.json', 'r') as f:
            return json.loads(f.read())
    except:
        return {}

def publish_infrastructure_update(infra):
    if infra is not None:
        report = infra.as_json()
        report["timestamp"] = time.time()*1000
        url = _SERVER+"/infrastructure"
        try:
            print(requests.post(url, json=report))
            print("-> Infrastructure published")
        except:
            print("-> Error while publishing infrastructure pdate")
        time.sleep(1)

def update_infrastructure(infra):
    if infra is not None:
        publish_infrastructure_update(infra)
        try:
            with open(_INFRA_PATH, "w+") as f:
                f.write(infra.as_kb())
        except FileNotFoundError as e:
            os.mkdir(os.path.dirname(_INFRA_PATH))
            with open(_INFRA_PATH, "w+") as f:
                f.write(infra.as_kb())

def exist_infrastructure():
    return os.path.exists(_INFRA_PATH)

def remove_infrastructure():
    if exist_infrastructure():
        os.remove(_INFRA_PATH)

def execute_cmd(cmd, background=False, timeout=EXECUTE_CMD_TIMEOUT):
    try:
        if background:
            subprocess.Popen(cmd, shell=True)
        else:
            p = subprocess.Popen(cmd.split(), shell=False)
            p.wait(timeout=timeout)
            return p.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"-> TIMEOUT for '{cmd}' ({timeout}s) expired")
        p_pid = os.getpgid(p.pid)
        os.killpg(p_pid, signal.SIGTERM)
        return False