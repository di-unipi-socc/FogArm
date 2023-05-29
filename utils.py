import os
import yaml
import json
import docker
import signal
import hashlib
import subprocess

_BASE_FOLDER = os.path.dirname(os.path.realpath(__file__))+"/"

client = docker.from_env()

EXECUTE_CMD_TIMEOUT = 3600

def dockerNodePs(machine_name):
    return [s.attrs['Spec']['Name'] for s in client.services.list()
        for _ in s.tasks({'node': machine_name, 
                          'desired-state': 'Running'})]

def get_current_placement(app=None):
    nodes = {}
    for n in client.nodes.list():
        node_name = n.attrs["Description"]["Hostname"]
        nodes[node_name] = dockerNodePs(node_name)
    placement = []
    for n,l in nodes.items():
        for s in l:
            if app is None:
                placement.append((s,n))
            elif s.startswith(app+"_"):
                placement.append((s[len(app+"_"):],n))
    return placement

def get_apps():
    try:   
        with open(_BASE_FOLDER+'/.tmp/.APPS.json', 'r') as f:
            return json.loads(f.read())
    except:
        return {}

def delete_app(app):
    apps = get_apps()
    if app in apps:
        del apps[app]
        with open(_BASE_FOLDER+'/.tmp/.APPS.json', 'w', encoding='utf-8') as f:
            json.dump(apps, f, ensure_ascii=False, indent=4)
    else:
        return False
    return True

def store_app(path):
    apps = get_apps()
    path = os.path.abspath(path)
    application = os.path.basename(os.path.normpath(path))
    try:
        with open(path+"/requirements.yml", "r") as stream:
            try:
                requirements = yaml.safe_load(stream)
                application = requirements["application"]
            except yaml.YAMLError as exc:
                print(exc)
    except:
        pass
    if application not in apps:
        if os.path.exists(path+"/docker-compose.yml"):
            apps[application] = path
            with open(_BASE_FOLDER+'.tmp/.APPS.json', 'w', encoding='utf-8') as f:
                json.dump(apps, f, ensure_ascii=False, indent=4)
        else:
            print("-> docker-compose Not Found in this Folder")
            return None
    else:
        print(f"-> An application called {application} already exist in {apps[application]}")
        return apps[application]
    return path

def hash_file(file):
    BLOCK_SIZE = 65536 # The size of each read from the file

    file_hash = hashlib.sha256() # Create the hash object, can use something other than `.sha256()` if you wish
    with open(file, 'rb') as f: # Open the file to read it's bytes
        fb = f.read(BLOCK_SIZE) # Read from the file. Take in the amount declared above
        while len(fb) > 0: # While there is still data being read from the file
            file_hash.update(fb) # Update the hash
            fb = f.read(BLOCK_SIZE) # Read the next block from the file

    return file_hash.hexdigest() # Get the hexadecimal digest of the hash

def execute_cmd(cmd, background=False, timeout=EXECUTE_CMD_TIMEOUT, cwd=None):
    try:
        if background:
            subprocess.Popen(cmd, shell=True, cwd=cwd)
        else:
            p = subprocess.Popen(cmd.split(), shell=False, cwd=cwd)
            p.wait(timeout=timeout)
            return p.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"-> TIMEOUT for '{cmd}' ({timeout}s) expired")
        p_pid = os.getpgid(p.pid)
        os.killpg(p_pid, signal.SIGTERM)
        return False

def my_query(s, prolog):
    try:
        q = prolog.query(s)
        result = next(q) 
        return result
    except StopIteration:
        return None

def parse_deployment(deployment):
    with open(deployment, "r") as f:
        deploy = (((f.readlines()[-1]).split(",[")[1]).split(",("))[0][:-1]
        deploy = deploy.split("on")
        placement = []
        for p in deploy:
            if p.startswith("("):
                t = p.replace("(","").replace(")","").split(",")
                placement.append((t[0],t[1]))

        return placement

def verify_placement(app):
    try:
        tmp_placement = parse_deployment(_BASE_FOLDER+".tmp/.placements/."+app)
    except:
        return False
    desired = []
    if tmp_placement is not None:
        for s,n in tmp_placement:
            desired.append((app+"_"+s,n))
    current = get_current_placement()
    for d in desired:
        if d not in current:
            return False
    for s,n in current:
        if s.startswith(app+"_") and (s,n) not in desired:
            return False       
    return True

def remove_deployment(app):
    try:
        os.remove(_BASE_FOLDER+".tmp/.placements/."+app)
        return True
    except:
        return False
