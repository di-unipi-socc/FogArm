import json
from os import mkdir
import time
import pymongo
import datetime
import argparse
import threading
import configparser
import random 

import fabric
import openstack

from utils import *
from fogMonMonitor import *

BASEPATH_FOGARMX = "/home/ubuntu/FogArmX"

VERBOSE = True

CONFIG_FILE = BASEPATH_FOGARMX+"/config.ini"

config = configparser.ConfigParser()
config.read(CONFIG_FILE)

COUNT = int(config["INFRA"]["count"])
CLOUDS = json.loads(config["INFRA"]["clouds"])#["garr-ct1", "garr-pa1"]#["garr-ct1", "garr-na", "garr-pa1", "garr-to1"], "garr-na", "garr-pa1", "garr-to1"]

IMAGE = "Ubuntu 20.04 - GARR"
FLAVOR = "d1.small"
NAME_PREFIX = "node"
KEYNAME = "socc"

SEC_GROUP = "FogArmX-sec-group"
SEC_GROUPS = ["default", SEC_GROUP]

NETWORK_ID = "default"

KEY_FILENAME = ""
PUBLIC_KEY = ""

GIT_USERNAME = ""
GIT_TOKEN = ""

REGISTRY_IP = ""
REGISTRY_CRT = ""
DAEMON_JSON = ""

FOGMON_SERVER = ""
FOGMON_IMAGE = "diunipisocc/liscio-fogmon:fogmon2"
FOGMON_PARAMS = {   
        "--time-report": 30,
        "--time-tests": 30,
        "--leader-check": 8,
        "--time-latency": 30,
        "--time-bandwidth": 600,
        "--heartbeat": 90,
        "--time-propagation": 20,
        "--max-per-latency": 100,
        "--max-per-bandwidth": 3,
        "--sensitivity": 15,
        "--hardware-window": 20,
        "--latency-window": 10,
        "--bandwidth-window": 5,
        "-t": 3,
    }

setup_script = [
    "sudo apt update",
    "sudo apt install -y python3-pip",
    "sudo pip3 install --upgrade pip",
    "sudo apt install -y docker.io",
    "sudo systemctl start docker",
    "sudo systemctl enable docker",
    "sudo usermod -aG docker ubuntu",
    "sudo apt install -y docker-compose",
    "sudo apt install -y dos2unix",
    "sudo git clone https://{}:{}@github.com/di-unipi-socc/FogArm.git".format(GIT_USERNAME, GIT_TOKEN),
    "sudo git config --global --add safe.directory /home/ubuntu/FogArm",
    'sudo git config --global user.email ""',
    'sudo git config --global user.name ""',
    "cd {} && sudo chmod +x run.sh".format(BASEPATH_FOGARMX),
    "cd {} && sudo dos2unix run.sh".format(BASEPATH_FOGARMX),
    "cd {} && sudo ./run.sh".format(BASEPATH_FOGARMX),
    "sudo mkdir /etc/docker/certs.d/",
    "sudo mkdir /etc/docker/certs.d/{}".format(REGISTRY_IP),
    "cd {}/GARR/ && sudo cp {} /etc/docker/certs.d/{}/ca.crt".format(BASEPATH_FOGARMX, REGISTRY_CRT, REGISTRY_IP),
    "cd {}/GARR/ && sudo cp {} /etc/docker/daemon.json".format(BASEPATH_FOGARMX, DAEMON_JSON),
    "sudo systemctl restart docker",
]

DATABASE_URL  = MONGO_URL = ""
DATABASE = pymongo.MongoClient(MONGO_URL).fogarmx

DELTA = int(config["EXPERIMENT"]["delta"])
APP_COUNT = int(config["EXPERIMENT"]["app_count"])
INTERVAL = int(config["EXPERIMENT"]["interval"])
VARIABILITY = float(config["EXPERIMENT"]["variability"])
INFRA_INTERVAL = int(config["EXPERIMENT"]["infra_interval"])

# Initialize and turn on debug logging
openstack.enable_logging(debug=False)

# Initialize connections
conns = {c:openstack.connect(cloud=c) for c in CLOUDS}

VMs = {}
vms_lock = threading.Lock()

IPs = {}

LEADER = "node0"+"-"+CLOUDS[0]

def reset_vms():
    # List the servers
    print("* Deleting VMs...")
    for conn in conns.values():
        for server in openstack.compute.v2.server.Server.list(session=conn.compute):
            if server.name.startswith(NAME_PREFIX):
                server.delete(session=conn.compute)
                if VERBOSE:
                    print("Deleted server: {}".format(server.name))
    print("* VMs Deleted")

def create_vm(name, cloud=None):
    if cloud is None:
        cloud = CLOUDS[0]
    conn = conns[cloud]
    t = 0
    while t < 20:
        try:
            return conn.create_server(name=name, 
                                image=IMAGE, 
                                flavor=FLAVOR, 
                                key_name=KEYNAME, 
                                security_groups=SEC_GROUPS, 
                                network=NETWORK_ID,
                                wait=True, 
                                auto_ip=True,
                                reuse_ips=True,
                                #ip_pool="floating-ip",
                                timeout=300
                                )
        except Exception as e:
            time.sleep(30)
            try:
                for server in openstack.compute.v2.server.Server.list(session=conn.compute):
                    if server.name == name:
                        server.delete(session=conn.compute)
            except:
                pass
            print("VM {} not created: {}. Retrying...".format(name,e))
            t+=1
            time.sleep(90)
    if t%10 == 0:
        print("VM {} - Error: {}".format(name, e))

    return None


def exec_script(host, script, hide=True):
    if VERBOSE:
        print("Executing script on {} ({})".format(IPs[host], host))
    retry = True
    status = None
    while retry:
        if VERBOSE:
            print("Trying to connect to {} ({})".format(IPs[host], host))
        try:
            vm = fabric.Connection(host, 
                                user='ubuntu',
                                connect_kwargs={
                                        "key_filename": KEY_FILENAME,
                                        },
                                #connect_timeout = 300
                                )
            if VERBOSE:
                print("Connected to {} ({})".format(IPs[host], host))
            for cmd in script:
                time.sleep(30)
                t = 0
                exc = None
                upper = 10
                while t < upper:
                    try:
                        status = vm.run(cmd, hide=hide, warn=True)
                        break
                    except Exception as e1:
                        print("Error while '{}': {} on {} ({}) [{}/{}]".format(cmd, e1, IPs[host], host, t+1, upper))
                        time.sleep(90)
                        exc = e1
                        t+=1

                if t == upper and exc is not None:
                    print("Failed to connect to {} ({})".format(IPs[host], host))
                    raise exc
            retry = False
        except Exception as e:
            if len(e.args) == 2 and ("Unable to connect" in e.args[1] or "Connection refused" in e.args[1] or "Encountered a bad command exit code" in e.args[1]): #"Timeout waiting for the server to come up" in e.args[1])
                retry = True
                time.sleep(180)
            else:
                print("VM: {} ({}) - Error: {}".format(IPs[host], host, e))
                retry = False
                status = None

    if VERBOSE:
        print("VM: {} ({}) executed".format(IPs[host], host))
    return status


def exec_script_thread(host, script, hide=True):
    #exec script in thread
    t = threading.Thread(target=exec_script, args=(host, script, hide))
    t.start()
    return t

class VMThread(threading.Thread):
    def __init__(self, vm_name, cloud=None):
        threading.Thread.__init__(self)
        self.vm_name = vm_name
        self.cloud = cloud
    def run(self):
        retry = True
        iteration = 0
        conn = conns[self.cloud]
        while retry:
            time.sleep(random.random() * 180)
            if VERBOSE:
                print("Creating VM: {}".format(self.vm_name))
            ip = create_vm(self.vm_name, self.cloud).access_ipv4

            print("VM: {} created".format(self.vm_name))

            with vms_lock:
                VMs[self.vm_name] = ip
                IPs[ip] = self.vm_name
                with open("VMs.json", "w+") as f:
                    json.dump(VMs, f)
                with open("IPs.json", "w+") as f:
                    json.dump(IPs, f)

            time.sleep(1200)
            if VERBOSE:
                print("Setting up VM: {}".format(self.vm_name))
            status = exec_script(ip, setup_script)
            if status is not None:
                print("* VM: {} setup completed".format(self.vm_name))

                with vms_lock:
                    VMs[self.vm_name] = ip
                    IPs[ip] = self.vm_name
                    with open("VMs.json", "w+") as f:
                        json.dump(VMs, f)
                    with open("IPs.json", "w+") as f:
                        json.dump(IPs, f)

                retry = False
            else:
                print("* VM: {} setup failed, retrying {}".format(self.vm_name, iteration))
                retry = True
                try:
                    for server in openstack.compute.v2.server.Server.list(session=conn.compute):
                        if server.name == self.vm_name :
                            server.delete(session=conn.compute)
                    if VERBOSE:
                        print("VM: {} deleted".format(self.vm_name))
                    
                    with vms_lock:
                        del VMs[self.vm_name] 
                        del IPs[ip]
                        with open("VMs.json", "w+") as f:
                            json.dump(VMs, f)
                        with open("IPs.json", "w+") as f:
                            json.dump(IPs, f)

                    time.sleep(120)
                except:
                    if VERBOSE:
                        print("VM: {} does not exist".format(self.vm_name))
                    time.sleep(60)

            iteration += 1
            if retry and iteration == 10:
                retry = False
                print("* CRITICAL - VM: {} setup failed".format(self.vm_name))

def test_nodes():
    exec_script(VMs[LEADER], ["cd {} && sudo python3 test.py".format(BASEPATH_FOGARMX)], hide=False)

def setup(num_vms=COUNT):
    global VMs
    global IPs

    VMs = {}
    IPs = {}
    reset_vms()
    time.sleep(180)

    print("* Releasing IPs...")
    for cloud in CLOUDS:
        conn = conns[cloud]
        conn.delete_unattached_floating_ips()

    print("* Creating VMs...")

    threads = []
    # Boot a server, wait for it to boot, and then do whatever is needed
    # to get a public IP address for it.
    for cloud in CLOUDS:
        for i in range(num_vms):
            name = NAME_PREFIX + str(i) + "-" + cloud
            t = VMThread(name, cloud)
            t.start()
            threads.append(t)

    for t in threads:
        t.join() 

    print("* VMs created")

    print(VMs)

    print("* Initialising Leader...")

    worker_cmd = ""

    while worker_cmd == "":
        time.sleep(30)
        try:
            res = exec_script(VMs[LEADER], ["sudo docker swarm init --advertise-addr {}:2377".format(VMs[LEADER])])
            for l in res.stdout.split("\n"):
                l = l.strip()
                if l.startswith("docker swarm join"):
                    worker_cmd = l
                    break
        except Exception as e:
            print("Error while initialising leader {} ({}): {}".format(LEADER, VMs[LEADER], e))


    print("* Initialising Workers...")

    threads = []

    for name,ip in VMs.items():
        if name != LEADER:
            threads.append(exec_script_thread(ip, ["sudo "+worker_cmd]))

    for t in threads:
        t.join()

    print("* Workers joined")

    exec_script(VMs[LEADER], ["sudo docker node ls", "sudo docker service ls"], hide=False)

    #print("* Creating Registry...")
    #exec_script(VMs[LEADER], [f"docker service create --name registry --publish published=5000,target=5000 registry:2"])

    time.sleep(30)
    
    print("* Running Tests...")
    test_nodes()
    
    print("* Setup complete")
    cec_status()

def start_fogmon(session):
    params = ""
    for k,v in FOGMON_PARAMS.items():
        params += "{} {} ".format(k,v)

    fogmon_leader_script = [
        "sudo docker pull {}".format(FOGMON_IMAGE), 
        "sudo docker run -d --name fogmon --net=host {} --leader -i {} -s {} {}".format(FOGMON_IMAGE, FOGMON_SERVER, session, params)
        ]
    fogmon_script = [
        "sudo docker pull {}".format(FOGMON_IMAGE), 
        "sudo docker run -d --name fogmon --net=host {} -C {} -i {} -s {} {}".format(FOGMON_IMAGE, VMs[LEADER], FOGMON_SERVER, session, params)
        ]

    threads = []

    exec_script(VMs[LEADER], fogmon_leader_script)

    time.sleep(60)
    for vm in VMs:
        if vm != LEADER:
            threads.append(exec_script_thread(VMs[vm], fogmon_script))

    for t in threads:
        t.join()

def stop_fogmon():
    threads = []

    for vm in VMs:
        threads.append(exec_script_thread(VMs[vm], ["sudo docker stop fogmon"]))

    for t in threads:
        t.join()

    threads = []

    for vm in VMs:
        threads.append(exec_script_thread(VMs[vm], ["sudo docker rm fogmon"]))

    for t in threads:
        t.join()

    for i in range(1,4):
        try:
            del_fogmon_session(i)
        except:
            pass

def clean_db():
    try:
        DATABASE.drop_collection("applications")
    except Exception as e:
        print("Error while cleaning database: {}".format(e))

    try:
        DATABASE.drop_collection("infrastructure")
    except Exception as e:
        print("Error while cleaning database: {}".format(e))

def experiment(delta, count, interval=INTERVAL, variability=VARIABILITY, infra_interval=INFRA_INTERVAL):
    print("Experiment: {}s".format(delta))

    print("Pusing to git")

    execute_cmd("sudo git -C {} add .".format(BASEPATH_FOGARMX))
    #execute_cmd("git commit -m \"Automatic Push - Running experiment: {} {} {} {}\"".format(delta, count, interval, variability))
    execute_cmd("sudo git -C {} commit -m C&C-Automatic-Push".format(BASEPATH_FOGARMX))
    execute_cmd("sudo git -C {} push https://{}:{}@github.com/di-unipi-socc/FogArm.git".format(BASEPATH_FOGARMX, GIT_USERNAME, GIT_TOKEN))

    git_pull()

    print("* Ready to start experiment")

    with open("IPs.json", "r") as f:
        IPs = json.load(f)

    nodes = []
    for ip in IPs.keys():
        nodes.append(ip)

    session = new_fogmon_session(nodes)

    print("Session: "+str(session))
    print("* Starting at {}".format(datetime.datetime.now()))
    start_fogmon(session)

    print("* Cleaning Database")
    clean_db()

    time.sleep(60)

    print("* Running experiment")
    print("pipeline.py {} {} {} {} {} {}".format(count, delta, interval, variability, session, infra_interval))
    exec_script(VMs[LEADER], ["cd {}/GARR/ && sudo python3 -u pipeline.py {} {} {} {} {} {} | sudo tee -a leader.log".format(BASEPATH_FOGARMX, count, delta, interval, variability, session, infra_interval)], hide=False)
    
    stop_fogmon()
    del_fogmon_session(session)
    print("* Experiment finished at "+str(datetime.datetime.now()))

    exec_script(VMs[LEADER], ["cd {} && sudo mkdir -p ./stats && sudo mkdir -p ./stats/$(date +%Y_%m_%d_%H) && sudo mv ./stats.json ./stats/$(date +%Y_%m_%d_%H)/stats.json && sudo cp {} ./stats/$(date +%Y_%m_%d_%H)/config.ini".format(BASEPATH_FOGARMX, CONFIG_FILE)], hide=True)
    exec_script(VMs[LEADER], ["cd {}/GARR/ && sudo rm -r ./apps".format(BASEPATH_FOGARMX)], hide=False)

    print("Pushing to git")
    git_push()

    print("* Experiment finished")
    print("Pulling")
    execute_cmd("sudo git pull https://{}:{}@github.com/di-unipi-socc/FogArm.git".format(GIT_USERNAME, GIT_TOKEN))


def setup_clouds(count):
    reset_vms()
    time.sleep(15)
    for cloud in CLOUDS:
        conn = conns[cloud]

        print(f"* Creating Security Groups on {cloud}...")
        if conn.get_security_group(SEC_GROUP) is not None:
            conn.delete_security_group(SEC_GROUP)

        conn.create_security_group(SEC_GROUP, "FogArmX security group")
        conn.create_security_group_rule(SEC_GROUP, 
                                        port_range_min=22, 
                                        port_range_max=22, 
                                        protocol="TCP", 
                                        remote_ip_prefix="0.0.0.0/0", 
                                        direction='ingress', 
                                        ethertype='IPv4')
        conn.create_security_group_rule(SEC_GROUP, 
                                        protocol="ICMP", 
                                        remote_ip_prefix="0.0.0.0/0", 
                                        direction='ingress', 
                                        ethertype='IPv4')
        print(f"* Security Groups created on {cloud}")

        print(f"* Creating Key Pair on {cloud}...")
        if conn.get_keypair(KEYNAME) is not None:
            conn.delete_keypair(KEYNAME)
        conn.create_keypair(KEYNAME, PUBLIC_KEY)
        print(f"* Key Pair created on {cloud}")

        # print(f"* Allocating {count} floating IPs on {cloud}...")
        # n = 0
        # for _ in range(count):
        #     try:
        #         conn.create_floating_ip()
        #         n+=1
        #     except:
        #         pass
        # print(f"* {n} floating IPs allocated on {cloud}")

        print("* Releasing IPs...")
        for cloud in CLOUDS:
            conn = conns[cloud]
            n = conn.delete_unattached_floating_ips()
            print(f"* {n} IPs released on {cloud}")
        print()


def cec_status():
    print("Status:")
    print("  Clouds:")
    for cloud in CLOUDS:
        print("    {}".format(cloud))
    try:
        print("  Leader: {} ({})".format(LEADER, VMs[LEADER]))
    except:
        pass
    print("  VMs:")
    for vm in VMs.keys():
        print("    {} ({})".format(vm, VMs[vm]))
    exec_script(VMs[LEADER], ["docker node ls", "docker service ls"], hide=False)
    exec_script(VMs[LEADER], ["sudo fax status"], hide=False)

def git_push():
    print("Pushing to git")
    exec_script(VMs[LEADER], [
        'sudo git config --global user.email ""',
        'sudo git config --global user.name ""',
        "cd {} && sudo git add . && sudo git commit -m \"Leader-Automatic-Push\" && sudo git push".format(BASEPATH_FOGARMX)], hide=False)

def git_pull():
    print("Pulling from git")
    threads = []
    for ip in IPs.keys():
        threads.append(exec_script_thread(ip, ["cd {} && sudo git stash && sudo git pull".format(BASEPATH_FOGARMX)]))

    for t in threads:
        t.join()

    print("Pulled")
    
        

def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)

if __name__ == "__main__":

    mkdir(BASEPATH_FOGARMX+"/infrastructure")
    
    with open("VMs.json", "r") as f:
        VMs = json.load(f)

    with open("IPs.json", "r") as f:
        IPs = json.load(f)
    try:
        print("Infrastructure:", VMs)
        print(f"Leader: {LEADER} ({VMs[LEADER]})")
    except:
        pass

    parser = argparse.ArgumentParser(prog='FogArm C&C')

    sp = parser.add_subparsers(dest='cmd')

    setup_parser = sp.add_parser('setup', help='Setup the C&C Network')
    setup_parser.add_argument('--count', type=int, default=COUNT, help='Number of VMs to create')

    setup_clouds_parser = sp.add_parser('setup-clouds', help='Setup the Clouds')
    setup_clouds_parser.add_argument('--count', type=int, default=COUNT, help='Number of floating IPs to create')

    delete_parser = sp.add_parser('delete', help='Delete the VMs')

    start_parser = sp.add_parser('start', help='Start the C&C Network Monitor')
    restart_parser = sp.add_parser('restart', help='Restart the C&C Network Monitor')

    stop_parser = sp.add_parser('stop', help='Stop the C&C Network Monitor')

    experiment_parser = sp.add_parser('experiment', help='Run an experiment')
    experiment_parser.add_argument('--delta', type=int, default=DELTA, help='Experiment duration in seconds')
    experiment_parser.add_argument('--count', type=int, default=APP_COUNT, help='Applications to run')
    experiment_parser.add_argument('--interval', type=int, default=INTERVAL, help='Interval between applications trigger in seconds')
    experiment_parser.add_argument('--variability', type=float, default=VARIABILITY, help='Variability of applications trigger')
    experiment_parser.add_argument('--infra', type=int, default=INFRA_INTERVAL, help='Interval between infrastructure update in seconds')

    test_parser = sp.add_parser('test', help='Test the C&C Network')

    status_parser = sp.add_parser('status', help='Status of the C&C Network')

    git_parser = sp.add_parser('git', help='Git on the C&C Network')

    git_sp = git_parser.add_subparsers(dest='op')

    git_sp.add_parser('push', help='Push the changes')
    git_sp.add_parser('pull', help='Pull the changes')

    args = parser.parse_args()

    if args.cmd == 'setup':
        setup(args.count)
    elif args.cmd == 'setup-clouds':
        setup_clouds(args.count)
    elif args.cmd == 'delete':
        reset_vms()
    elif args.cmd == 'start':
        nodes = []
        for ip in IPs.keys():
            nodes.append(ip)
        session = new_fogmon_session(nodes)
        print("Session: "+str(session))
        print("Starting at {}".format(datetime.datetime.now()))
        start_fogmon(session)
    elif args.cmd == 'stop':
        stop_fogmon()
    elif args.cmd == 'restart':
        stop_fogmon()
        nodes = []
        for ip in IPs.keys():
            nodes.append(ip)
        session = new_fogmon_session(nodes)
        print("Session: "+str(session))
        print("Starting at {}".format(datetime.datetime.now()))
        start_fogmon(session)
    elif args.cmd == 'experiment':
        experiment(args.delta, args.count, args.interval, args.variability, args.infra)
    elif args.cmd == 'test':
        test_nodes()
    elif args.cmd == 'status':
        cec_status()
    elif args.cmd == 'git':
        if args.op == 'push':
            git_push()
        else:
            git_pull()
    else:
        parser.print_help()
        exit(1)

    exit(0)
