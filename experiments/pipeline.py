import os
import sys
import time
import shutil
import random
import threading

from distutils.dir_util import copy_tree

from utils import *
import fogMonMonitor as fm

BASE = os.path.dirname(os.path.realpath(__file__))
APPS = "apps"
REPO = "docker-swarm-demo"

class Module:
    def __init__(self, name, blueprints, compose, available):
        self._name = name
        self._blueprints = blueprints
        self._compose = compose
        self._available = available
        
    def get_name(self):
        return self._name

    def process(self):
        if random.random() < self._available:
            return (random.choice(self._blueprints),self._compose)
        else:
            return None
class Pipeline:
    def __init__(self, path):
        self._path = path
        self._modules = []

    def get_path(self):
        return self._path

    def add_module(self, module):
        self._modules.append(module)

    def run(self):
        requirements = []
        for module in self._modules:
            req = module.process()
            if req is not None:
                requirements.append((module.get_name(),req))

        with open(self._path+"/requirements.yml", "w+") as f:
            f.write("services:")
            for module,(requirement,_) in requirements:
                f.write(f"\n  {module}:\n")
                f.write(f"    {requirement}\n")

        with open(self._path+"/docker-compose.yml", "w+") as f:
            f.write("version: '3.2'\n")
            f.write("services:")
            for module,(_,compose) in requirements:
                f.write(f"\n  {module}:\n")
                f.write(f"    {compose}\n")

def mkdir(path):
    if not os.path.exists(path):
      os.makedirs(path)

def rmdir(path):
    if os.path.exists(path):
      shutil.rmtree(path)

def remove_all_apps():
  for a in get_apps():
    execute_cmd(f"sudo fax rm {a}")
    print(f"Pipeline {a} removed from fogarmx")
    time.sleep(1)

measured_hw = {
  "api-gateway": 0.25,
  "customers": 0.5,
  "customers_db": 0.25,
  "invoices": 0.5,
  "invoices_db": 0.25,
  "products": 0.25,
  "products_db": 0.5,
  "webapp": 0.25
}

HIGH_PERFORMANCE = 0.25

def setup_pipeline(path):
    pipeline = Pipeline(path)

    # Add modules   
    pipeline.add_module(Module("customers",
    [f"hardware: {measured_hw['customers']}\n\
    links:\n\
      customers_db:\n\
        bandwidth: 15\n\
        latency: 300\n",
    f"hardware: {measured_hw['customers']+(measured_hw['customers']*HIGH_PERFORMANCE)}\n\
    links:\n\
      customers_db:\n\
        bandwidth: 30\n\
        latency: 200\n"],
    "build: customers-service\n\
    image: embair/swarm-demo:customers\n\
    environment:\n\
      - REDIS_HOST=customers_db\n\
    links:\n\
      - customers_db\n",
    0.9))

    pipeline.add_module(Module("customers_db",
    [f"hardware: {measured_hw['customers_db']}\n",
    f"hardware: {measured_hw['customers_db']+(measured_hw['customers_db']*HIGH_PERFORMANCE)}\n"],
    "image: redis\n",
    1))

    pipeline.add_module(Module("products",
    [f"hardware: {measured_hw['products']}\n\
    links:\n\
      products_db:\n\
        bandwidth: 15\n\
        latency: 300\n",
    f"hardware: {measured_hw['products']+(measured_hw['products']*HIGH_PERFORMANCE)}\n\
    links:\n\
      products_db:\n\
        bandwidth: 30\n\
        latency: 200\n"],
    "build: products-service\n\
    image: embair/swarm-demo:products\n\
    environment:\n\
      - REDIS_HOST=products_db\n\
    links:\n\
      - products_db\n",
    0.9))

    pipeline.add_module(Module("products_db",
    [f"hardware: {measured_hw['products_db']}\n",
    f"hardware: {measured_hw['products_db']+(measured_hw['products_db']*HIGH_PERFORMANCE)}\n"],
    "image: redis\n",
    1))

    pipeline.add_module(Module("invoices",
    [f"hardware: {measured_hw['invoices']}\n\
    links:\n\
      invoices_db:\n\
        bandwidth: 15\n\
        latency: 300\n\
      products:\n\
        bandwidth: 10\n\
        latency: 400\n\
      customers:\n\
        bandwidth: 10\n\
        latency: 400\n",
    f"hardware: {measured_hw['invoices']+(measured_hw['invoices']*HIGH_PERFORMANCE)}\n\
    links:\n\
      invoices_db:\n\
        bandwidth: 30\n\
        latency: 200\n\
      products:\n\
        bandwidth: 20\n\
        latency: 300\n\
      customers:\n\
        bandwidth: 20\n\
        latency: 300\n"],
    "build: invoices-service\n\
    image: embair/swarm-demo:invoices\n\
    environment:\n\
      - REDIS_HOST=invoices_db\n\
      - CUSTOMERS_API=http://customers:8080\n\
      - PRODUCTS_API=http://products:8080\n\
    links:\n\
      - invoices_db\n",
    0.9))

    pipeline.add_module(Module("invoices_db",
    [f"hardware: {measured_hw['invoices_db']}\n",
    f"hardware: {measured_hw['invoices_db']+(measured_hw['invoices_db']*HIGH_PERFORMANCE)}\n"],
    "image: redis\n",
    1))

    pipeline.add_module(Module("webapp",
    [f"hardware: {measured_hw['webapp']}\n\
    links:\n\
      api-gateway:\n\
        bandwidth: 10\n\
        latency: 200\n",
    f"hardware: {measured_hw['webapp']+(measured_hw['webapp']*HIGH_PERFORMANCE)}\n\
    links:\n\
      api-gateway:\n\
        bandwidth: 30\n\
        latency: 200\n"],
    "build: webapp\n\
    image: embair/swarm-demo:webapp\n",
    0.75))

    pipeline.add_module(Module("api-gateway",
    [f"hardware: {measured_hw['api-gateway']}\n\
    links:\n\
      invoices:\n\
        bandwidth: 15\n\
        latency: 750\n\
      products:\n\
        bandwidth: 15\n\
        latency: 750\n\
      customers:\n\
        bandwidth: 15\n\
        latency: 750\n\
      webapp:\n\
        bandwidth: 10\n\
        latency: 400\n",
    f"hardware: {measured_hw['api-gateway']+(measured_hw['api-gateway']*HIGH_PERFORMANCE)}\n\
    links:\n\
      invoices_db:\n\
        bandwidth: 30\n\
        latency: 400\n\
      products:\n\
        bandwidth: 7\n\
        latency: 400\n\
      customers:\n\
        bandwidth: 7\n\
        latency: 400\n\
      webapp:\n\
        bandwidth: 7\n\
        latency: 200\n"],
    "build: api-gateway\n\
    image: nginx:latest\n\
    links:\n\
      - customers\n\
      - products\n\
      - invoices\n\
      - webapp\n",
    0.8))

    return pipeline

def setup_pipelines(count):
    
    rmdir(f"{BASE}/{APPS}")
    mkdir(f"{BASE}/{APPS}/")

    pipelines = []

    for count in range(int(count)):
        pipeline = f"{BASE}/{APPS}/{REPO}-{count}"
        mkdir(f"{pipeline}")
        copy_tree(f"{BASE}/{REPO}/", f"{pipeline}")
        pipelines.append(setup_pipeline(pipeline))
        pipelines[-1].run()
        print(f"Pipeline {count} created")
        try:
          execute_cmd(f"sudo fax add {pipeline}/")
        except:
          pass
        print(f"Pipeline {count} added to fogarmx")
        time.sleep(5)

    return pipelines

def execute_pipelines(pipelines, delta, interval, variability):
    print("Execute pipelines")

    start_time = time.time()

    while time.time() - start_time < delta:
        print(time.time() - start_time)
        time.sleep(interval)
        for pipeline in pipelines:
            if random.random() < variability:
                print(f"Pipeline {pipeline.get_path()} triggered")
                try:
                  pipeline.run()
                  print(f"Pipeline {pipeline.get_path()} executed")
                except Exception as e:
                  print(e)
                  pass
                ##time.sleep(random.randint(1, min(interval, 60)))

    print("Execute pipelines finished")

    remove_all_apps()
    
    print("Time elapsed: "+str(time.time() - start_time))


if __name__ == "__main__":
    
    count = int(sys.argv[1]) if len(sys.argv) >= 2 else 1
    delta = int(sys.argv[2]) if len(sys.argv) >= 3 else 900
    interval = int(sys.argv[3]) if len(sys.argv) >= 4 else 60
    variability = float(sys.argv[4]) if len(sys.argv) >= 5 else 0.5
    session = int(sys.argv[5]) if len(sys.argv) >= 6 else 1
    infra_interval = int(sys.argv[6]) if len(sys.argv) >= 7 else 60
    seed = int(sys.argv[7]) if len(sys.argv) >= 8 else 42
    
    print("Starting experiment...")
    print("Apps: "+str(count))
    print("Delta: "+str(delta))
    print("Interval: "+str(interval))
    print("Variability: "+str(variability))
    print("Session: "+str(session))
    print("Infra Interval: "+str(infra_interval))
    print("Seed: "+str(seed))

    random.seed(seed)
    
    print("FogArmX removing all...")
    remove_all_apps()
    print("FogArmX removing all finished")

    time.sleep(30)

    threads = []

    threads.append(threading.Thread(target=fm.execute_experiment, args=(session,delta*1000,infra_interval,seed)))
    threads[0].setDaemon(True)
    threads[0].start()
    print("Launched FogMonMonitor")
    time.sleep(30)

    print("Waiting Infrastructure...")

    while not exist_infrastructure():
      time.sleep(5)
    
    print("Infrastructure detected")
    time.sleep(15)
    print("Setting up pipelines...")
    pipelines = setup_pipelines(count)

    time.sleep(30)
    print("FogArmX restarting FogWatcher...")
    execute_cmd("sudo fax watcher restart")
    time.sleep(30)

    print("Executing pipelines...")

    execute_pipelines(pipelines, delta, interval, variability)

    rmdir(f"{BASE}/{APPS}")

    execute_cmd("sudo fax watcher stop")
    
