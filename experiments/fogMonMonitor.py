import json
import time
import shutil
import random
import requests
import hashlib
import yaml
import docker

from utils import *

NODE_FAILURE_THRESHOLD = 0.05
LINK_FAILURE_THRESHOLD = 0.05

FOGMON_SERVER = ""

class Node:
    def __init__(self, name, sw=[], hw=0, iot=[]):
        self._name = name
        self._sw = sw
        self._hw = hw
        self._iot = iot
        self._failed = False

    def as_fact(self):
        if self._failed:
            return ""
        sw = "["+", ".join(self._sw)+"]"
        iot = "["+", ".join(self._iot)+"]"
        return f"node({self._name}, {sw}, {self._hw}, {iot}).".replace("'","")

    def as_json(self):
        if self._failed:
            return {}
        return {
            "name": self._name,
            "sw": self._sw,
            "hw": self._hw,
            "iot": self._iot,
        }

    def get_name(self):
        return self._name

    def set_sw(self, sw):
        if sw is not None:
            self._sw = sw

    def set_hw(self, hw):
        if hw is not None:
            self._hw = hw

    def set_iot(self, iot):
        if iot is not None:
            self._iot = iot

    def set_failed(self, failed):
        self._failed = failed

    def get_failed(self):
        return self._failed

    def get_sw(self):
        return self._sw

    def get_hw(self):
        return self._hw

    def get_iot(self):
        return self._iot


class Link:
    def __init__(self, n1, n2, bw="inf", lat=0):
        self._n1 = n1
        self._n2 = n2
        self._bw = bw
        self._lat = lat
        self._failed = False

    def as_fact(self):
        if self._failed:
            return ""
        return f"link({self._n1}, {self._n2}, {self._lat}, {self._bw})."

    def as_json(self):
        if self._failed:
            return {}
        return {
            "source": self._n1,
            "dest": self._n2,
            "bw": self._bw,
            "lat": self._lat,
        }

    def get_n1(self):
        return self._n1

    def get_n2(self):
        return self._n2

    def set_bw(self, bw):
        if bw is not None:
            self._bw = bw

    def set_lat(self, lat):
        if lat is not None:
            self._lat = lat
    
    def set_failed(self, failed):
        self._failed = failed

    def get_bw(self):
        return self._bw

    def get_lat(self):
        return self._lat

    def get_failed(self):
        return self._failed

class Infrastructure:
    def __init__(self):
        self._nodes_name = []
        self._nodes = []
        self._link = []

    def add_node(self, n):
        self._nodes_name.append(n.get_name())
        self._nodes.append(n)

    def add_link(self, link):
        self._link.append(link)

    def as_kb(self):
        kb = f":-dynamic deployment/3.\n\
:-dynamic application/2.\n\
:-dynamic service/4.\n\
:-dynamic s2s/4.\n\
:-dynamic link/4.\n\
:-dynamic node/4.\n\n"
        for n in self.get_nodes():
            kb += n.as_fact()+"\n"
        kb += "\n"
        for link in self.get_links():
            kb += link.as_fact()+"\n"
        kb += "\n"

        return kb

    def as_json(self):
        json_dict = {}
        json_dict["nodes"] = {}
        for n in self.get_nodes():
            r = n.as_json()
            if r != {}:
                json_dict["nodes"][n.get_name()] = r
        json_dict["links"] = {}
        for l in self.get_links():
            r = l.as_json()
            if r != {}:
                if l.get_n1() in json_dict["links"]:
                    json_dict["links"][l.get_n1()][l.get_n2()] = r
                else:
                    json_dict["links"][l.get_n1()] = {l.get_n2(): r}
        return json_dict


    def set_node(self, node_name, sw=None, hw=None, iot=None, failed=False):
        for n in self._nodes:
            if n.get_name() == node_name:
                n.set_sw(sw)
                n.set_hw(hw)
                n.set_iot(iot)
                n.set_failed(failed)

    def set_link(self, n1, n2, bw=None, lat=None, failed=False):
        for l in self._link:
            if l.get_n1() == n1 and l.get_n2() == n2:
                l.set_bw(bw)
                l.set_lat(lat)
                l.set_failed(failed)

    def get_nodes(self):
        random.shuffle(self._nodes)
        return self._nodes

    def get_links(self):
        random.shuffle(self._link)
        return self._link

    def get_link(self, n1, n2):
        for l in self._link:
            if l.get_n1() == n1 and l.get_n2() == n2:
                return l
        return None

    def get_node(self, node_name):
        for n in self._nodes:
            if n.get_name() == node_name:
                return n
        return None

client = docker.from_env()

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

def get_requirements(path):
    try:
        with open(path+"/docker-compose.yml", "r") as stream:
            try:
                compose = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
    except FileNotFoundError as exc:
        print("-> docker-compose Not Found in this Folder")
        return None

    try:
        with open(path+"/requirements.yml", "r") as stream:
            try:
                requirements = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
    except FileNotFoundError as exc:
        requirements = None

    reqs_dict = {"services":{}, "s2s":{}}

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
                                    if s not in reqs_dict["s2s"]:
                                        reqs_dict["s2s"][s] = {}
                                    reqs_dict["s2s"][s][e] = {
                                        "latency": lat,
                                        "bandwidth": bw
                                    }
            reqs_dict["services"][s] = {
                "software": sw,
                "hardware": hw,
                "iot": iot
            }

    return reqs_dict

def dynamic_infrastructure(infra):
    bw_alloc = {}
    hw_alloc = {}
    if infra is not None:
        for a,path in get_apps().items():
            placement = get_current_placement(a)
            dict_placement = {}
            for s,n in placement:
                    dict_placement[s] = n
            reqs = get_requirements(path)
            if reqs is not None:
                for s1 in reqs["s2s"]:
                    for s2 in reqs["s2s"][s1]:
                        if s1 in dict_placement and s2 in dict_placement:
                            n1 = dict_placement[s1]
                            n2 = dict_placement[s2]
                            if n1 not in bw_alloc:
                                bw_alloc[n1] = {}
                            if n2 not in bw_alloc[n1]:
                                bw_alloc[n1][n2] = 0
                            bw_alloc[n1][n2] += reqs["s2s"][s1][s2]["bandwidth"]
                            #print(s1, s2, reqs["s2s"][s1][s2]["bandwidth"],n1,n2)

                for s in reqs["services"]:
                    if s in dict_placement:
                        n = dict_placement[s]
                        if n not in hw_alloc:
                            hw_alloc[n] = 0
                        hw_alloc[n] += reqs["services"][s]["hardware"]
                        #print(s, reqs["services"][s]["hardware"],n)
            #print(bw_alloc)
            #print(hw_alloc)
                            

        for n in infra.get_nodes():
            if random.random() < NODE_FAILURE_THRESHOLD:
                n.set_failed(True)
            else:
                if n.get_name() in hw_alloc:
                    n.set_hw(n.get_hw() - hw_alloc[n.get_name()] - ((float(n.get_hw()*0.25))*random.gauss(0.5,0.25)))
        for l in infra.get_links():
            if random.random() < LINK_FAILURE_THRESHOLD:
                l.set_failed(True)
            else:
                n1 = l.get_n1()
                n2 = l.get_n2()
                if n1 in bw_alloc and n2 in bw_alloc[n1]:
                    l.set_bw(l.get_bw() - bw_alloc[n1][n2] - ((float(l.get_bw()*0.25))*random.gauss(0.5,0.25)))
                    l.set_lat(l.get_lat() + int(random.gauss(50,25)))

        return infra
    else:
        return None

REPORT_HASH = ""

def parse_fogmon_report(report):
    global REPORT_HASH
    if report is not None and report["status"] is True:

        report = report["data"]

        report = json.dumps(report)
        new_hash = hashlib.sha256(report.encode('utf-8')).hexdigest()

        if REPORT_HASH == new_hash:
            print("Report is the same")
            return None

        REPORT_HASH = new_hash

        with open("IPs.json", "r") as f:
            IPs = json.load(f)

        for ip,vm in IPs.items():
            report = report.replace(ip,vm)

        report = json.loads(report)

        infra = Infrastructure()

        for node,caps in report["hardware"].items():
            n = Node(node, ["docker"], float(float(caps["mean_free_memory"])/pow(1024,3)), []) #HW in bytes now GB
            infra.add_node(n)

        for _,src in IPs.items():
            for _,dst in IPs.items():
                if src != dst:
                    try:
                        link = Link(src, dst, float(float(report["matrix"]["B"][src][dst]["mean"])/1024), int(report["matrix"]["L"][src][dst]["mean"])) #BW in kbits now Mbits
                        infra.add_link(link)
                    except:
                        pass

        return infra

    return None

def new_fogmon_session(nodes):
    res = requests.post("http://"+FOGMON_SERVER+"/testbed", json={"nodes":nodes, "monitor":True})
    if res.status_code != 201:
        print("Failed to register testbed")
        print(res, res.json())
        return None
    else:
        session = res.json()["session"]

    return session

def del_fogmon_session(session):
    res = requests.get("http://"+FOGMON_SERVER+"/testbed/"+str(session)+"/removeall")
    print(res, res.json())

def get_fogmon_report(session):
    try:
        res = requests.get("http://"+FOGMON_SERVER+"/testbed/"+str(session)+"/monitor")
        try:
            print(res, str(res.json())[:50])
        except:
            print(res)
        return res.json()
    except:
        print("Failed to get report")
        return None

def execute_experiment(session, delta=60, interval=5, seed=42):

    random.seed(seed)

    remove_infrastructure()

    start_time = time.time()

    while time.time() - start_time < delta:
        update_infrastructure(dynamic_infrastructure(parse_fogmon_report(get_fogmon_report(session))))
        time.sleep(interval)
    
    print("Time elapsed: "+str(time.time() - start_time))

def mkdir(path):
    if not os.path.exists(path):
      os.makedirs(path)
      
def rmdir(path):
    if os.path.exists(path):
      shutil.rmtree(path)

if __name__ == "__main__":
    
    import sys
    import time

    if len(sys.argv) != 5:
        print("Usage: "+sys.argv[0]+" <session> <delta> <interval> <seed>")
        exit(1)
    
    print("Starting experiment...")
    print("Session: "+sys.argv[1])
    print("Delta: "+sys.argv[2])
    print("Interval: "+sys.argv[3])
    print("Seed: "+sys.argv[4])

    execute_experiment(int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))

    



